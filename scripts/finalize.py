"""Verify final packaging after removing build tools; application code/dependencies unchanged."""
import hashlib, json, statistics, shutil, time, sys
from pathlib import Path
from experiment import ROOT, OUT, cmd, compose, api, ready, body, save

def main():
    # Preserve exact evidence for the image used for performance measurements.
    for name in ('image.json','startup.json','build-first.log','build-second.log'):
        target=OUT/('benchmark-'+name)
        if not target.exists(): shutil.copyfile(OUT/name,target)
    app_hash=hashlib.sha256((ROOT/'app.py').read_bytes()).hexdigest()
    first=compose('build','--progress=plain','web')
    first_image=json.loads(cmd('docker','image','inspect','vaccinations-pr1:local'))[0]
    second=compose('build','--progress=plain','web')
    image=json.loads(cmd('docker','image','inspect','vaccinations-pr1:local'))[0]
    digest='debian:12-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587'
    base=json.loads(cmd('docker','image','inspect',digest))[0]
    layers=base['RootFS']['Layers']
    assert first_image['RootFS']['Layers'][:len(layers)]==layers==image['RootFS']['Layers'][:len(layers)]
    (OUT/'build-first.log').write_text(first,encoding='utf-8')
    (OUT/'build-second.log').write_text(second,encoding='utf-8')
    save('image.json',dict(size_bytes=image['Size'],image_id=image['Id'],base_digest=digest,base_layers=layers,service_layers=image['RootFS']['Layers'],same_base_layers=True,first_build_base_layers=first_image['RootFS']['Layers'][:len(layers)],second_build_base_layers=image['RootFS']['Layers'][:len(layers)]))
    starts=[]
    for i in range(3):
        print(f'Final runtime empty-volume startup {i+1}/3',flush=True)
        compose('down','-v'); origin=time.perf_counter()
        compose('up','-d','--scale','web=1'); ready()
        starts.append(time.perf_counter()-origin)
    save('startup.json',dict(seconds=starts,median_seconds=statistics.median(starts)))
    journal=[]
    created=api('POST','/vaccinations',body(7),201); journal.append(created)
    path=f"/vaccinations/{created['body']['id']}"
    journal.extend([api('GET',path,expected=200),api('PUT',path,body(8),200),api('DELETE',path,expected=204),api('DELETE',path,expected=404)])
    journal.append(api('POST','/vaccinations',dict(body(7),dose_number=5),400))
    for i in range(100): api('POST','/vaccinations',body(i),201)
    journal.append(api('GET','/vaccinations?limit=10&vaccine=MMR',expected=200))
    audit=compose('exec','-T','web','python','-c',"import importlib.util,shutil,json,hashlib; absent={k:importlib.util.find_spec(k) is None for k in ('pip','setuptools','wheel')}; assert all(absent.values()); assert not shutil.which('gcc') and not shutil.which('make'); print(json.dumps({'absent':absent,'gcc':shutil.which('gcc'),'make':shutil.which('make'),'app_sha256':hashlib.sha256(open('/app/app.py','rb').read()).hexdigest()}))")
    audit=json.loads(audit); assert audit['app_sha256']==app_hash
    container=compose('ps','-q','web').strip()
    limits=json.loads(cmd('docker','inspect','--format','{{json .HostConfig}}',container))
    assert limits['NanoCpus']==1500000000 and limits['Memory']==1073741824
    save('final-runtime-checks.json',journal)
    save('final-runtime.json',dict(audit=audit,cpu_limit=limits['NanoCpus']/1e9,memory_limit_bytes=limits['Memory'],note='Performance series used the same app and runtime dependencies before removal of unused packaging tools. Final image size/startup and CRUD rechecked.'))
    cmd('powershell','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'start.ps1'))
    save('start-command.json',dict(success=True,health=api('GET','/healthz',expected=200)))
    cmd(sys.executable,str(ROOT/'scripts/report.py'))
    print('Final image, startup, limits and single-command launcher verified.',flush=True)
if __name__=='__main__': main()
