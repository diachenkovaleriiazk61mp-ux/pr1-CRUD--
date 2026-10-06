"""Collect real Docker evidence and regenerate the report. Destructive reset is explicit."""
import argparse, json, os, platform, statistics, subprocess, sys, time, urllib.request, urllib.error
from datetime import date, timedelta
from pathlib import Path
from loadgen import run_open, run_closed
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'results'
BASE='http://127.0.0.1:'+os.environ.get('PORT','18080')

def cmd(*args):
    r=subprocess.run(args,cwd=ROOT,text=True,encoding='utf-8',errors='replace',capture_output=True)
    if r.returncode:
        raise RuntimeError(' '.join(args)+'\n'+r.stderr+'\n'+r.stdout)
    return r.stdout+r.stderr if 'build' in args else r.stdout

def compose(*args): return cmd('docker','compose',*args)
def save(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def api(method,path,data=None,expected=None):
    req=urllib.request.Request(BASE+path,data=json.dumps(data).encode() if data is not None else None,
                              headers={'Content-Type':'application/json'},method=method)
    try:
        r=urllib.request.urlopen(req,timeout=5)
    except urllib.error.HTTPError as e: r=e
    body=r.read().decode(); result=dict(method=method,path=path,status=r.code,body=json.loads(body) if body else None,instance=r.headers.get('X-Instance-ID'))
    if expected is not None and r.code!=expected: raise AssertionError(result)
    return result

def ready(timeout=90):
    end=time.perf_counter()+timeout
    while time.perf_counter()<end:
        try:
            if api('GET','/healthz')['status']==200: return
        except Exception: pass
        time.sleep(.1)
    raise TimeoutError('healthz did not become ready')

def body(i=0):
    return dict(patient_code=f'P{i:03}',vaccine='MMR' if i%2==0 else 'HepB',batch='B007',dose_number=1,administration_date=date.today().isoformat(),facility='Clinic 7')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--reset-lab-data',action='store_true',help='Allow deleting only this Compose project volume')
    p.add_argument('--processes',type=int)
    p.add_argument('--threads',type=int,default=64,help='Threads per generator process; 64 preserves the submitted measurement setup')
    p.add_argument('--reuse-calibration',action='store_true',help='Reuse verified no-op results on this same unchanged machine')
    a=p.parse_args()
    if not a.reset_lab_data:
        p.error('The required empty-volume tests need --reset-lab-data (deletes this lab database).')
    OUT.mkdir(exist_ok=True)
    print('Checking Docker Engine',flush=True)
    cmd('docker','info')
    if not (ROOT/'.env').exists():
        import secrets
        (ROOT/'.env').write_text('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\nPOSTGRES_USER=vaccinations\nPOSTGRES_DB=vaccinations\nPORT=18080\n')
    for line in (ROOT/'.env').read_text().splitlines():
        if line.startswith('PORT='):
            global BASE
            BASE='http://127.0.0.1:'+line.split('=',1)[1]
    save('machine.json',dict(platform=platform.platform(),cores=os.cpu_count(),generator_same_host=True,generator_processes=a.processes,generator_threads=a.threads,docker=cmd('docker','version'),compose=compose('version')))
    if not a.reuse_calibration:
        # No-op check precedes service measurements; keep every raw request.
        noop=subprocess.Popen([sys.executable,str(ROOT/'scripts/noop.py')],cwd=ROOT)
        try:
            time.sleep(1)
            for rate in (10,100,500):
                print(f'No-op calibration {rate} rps',flush=True)
                run_open('http://127.0.0.1:8099/',rate,10,a.processes,a.threads)
                result=run_open('http://127.0.0.1:8099/',rate,30,a.processes,a.threads)
                save(f'noop-{rate}.json',result)
        finally:
            noop.terminate(); noop.wait()
    else:
        for rate in (10,100,500):
            calibration=json.loads((OUT/f'noop-{rate}.json').read_text(encoding='utf-8'))['summary']
            assert calibration['sent_rps']>=.98*rate and calibration['non_2xx_fraction']==0
        print('Reusing verified no-op calibration on the same machine',flush=True)
    print('Building twice and verifying base layers',flush=True)
    first=compose('build','--progress=plain','web')
    first_layers=json.loads(cmd('docker','image','inspect','vaccinations-pr1:local'))[0]['RootFS']['Layers']
    second=compose('build','--progress=plain','web')
    (OUT/'build-first.log').write_text(first)
    (OUT/'build-second.log').write_text(second)
    image=json.loads(cmd('docker','image','inspect','vaccinations-pr1:local'))[0]
    digest='debian:12-slim@sha256:7c7b2c966bc9ee8cedfeef67e0e279108992c77681fa595db4a9d65c06ccc587'
    cmd('docker','pull',digest)
    base=json.loads(cmd('docker','image','inspect',digest))[0]
    assert image['RootFS']['Layers'][:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']
    assert first_layers[:len(base['RootFS']['Layers'])]==base['RootFS']['Layers']
    save('image.json',dict(size_bytes=image['Size'],base_digest=digest,base_layers=base['RootFS']['Layers'],service_layers=image['RootFS']['Layers'],same_base_layers=True,first_build_base_layers=first_layers[:len(base['RootFS']['Layers'])],second_build_base_layers=image['RootFS']['Layers'][:len(base['RootFS']['Layers'])]))
    compose('pull','db','lb')
    starts=[]
    for start_index in range(3):
        print(f'Empty-volume startup {start_index+1}/3',flush=True)
        compose('down','-v')
        started=time.perf_counter()
        compose('up','-d','--scale','web=1')
        ready()
        starts.append(time.perf_counter()-started)
    save('startup.json',dict(seconds=starts,median_seconds=statistics.median(starts)))
    print('CRUD, validation, persistence and readiness checks',flush=True)
    journal=[]
    created=api('POST','/vaccinations',body(),201); journal.append(created)
    ident=created['body']['id']; path=f'/vaccinations/{ident}'
    journal.extend([api('GET','/vaccinations',expected=200),api('GET',path,expected=200),api('PUT',path,body(1),200),api('DELETE',path,expected=204),api('DELETE',path,expected=404),api('GET',path,expected=404)])
    for dose in (0,5): journal.append(api('POST','/vaccinations',dict(body(),dose_number=dose),400))
    journal.append(api('POST','/vaccinations',dict(body(),administration_date=(date.today()+timedelta(days=1)).isoformat()),400))
    journal.append(api('PUT',path,{'vaccine':'MMR'},400))
    journal.append(api('GET','/vaccinations?limit=101',expected=400))
    persisted=api('POST','/vaccinations',body(99),201)['body']
    compose('down'); compose('up','-d','--scale','web=1'); ready()
    journal.append(api('GET',f"/vaccinations/{persisted['id']}",expected=200))
    compose('down','-v'); compose('up','-d','--scale','web=1'); ready()
    empty=api('GET','/vaccinations',expected=200); assert empty['body']['total']==0
    journal.append(empty)
    ids=[api('POST','/vaccinations',body(i),201)['body']['id'] for i in range(100)]
    filtered=api('GET','/vaccinations?vaccine=MMR&limit=10&offset=5',expected=200)
    assert filtered['body']['total']==50 and len(filtered['body']['items'])==10
    journal.append(filtered)
    # Verify readiness reports 503 while PostgreSQL is actually stopped.
    compose('stop','db')
    journal.append(api('GET','/healthz',expected=503))
    compose('start','db'); ready()
    save('checks.json',journal)
    url=BASE+f'/vaccinations/{ids[0]}'
    for replicas in (1,2):
        compose('up','-d','--wait','--scale',f'web={replicas}'); time.sleep(3)
        for rate in (10,100,500):
            for repeat in range(1,4):
                print(f'Open loop: replicas={replicas}, rate={rate}, repeat={repeat}',flush=True)
                run_open(url,rate,10,a.processes,a.threads)
                save(f'open-{replicas}-{rate}-{repeat}.json',run_open(url,rate,30,a.processes,a.threads))
        (OUT/f'lb-{replicas}.log').write_text(compose('logs','--no-color','lb'),encoding='utf-8')
    compose('up','-d','--wait','--scale','web=1'); time.sleep(3)
    print('Closed-loop comparison',flush=True)
    candidates=[]
    for rate in (10,100,500):
        runs=[json.loads((OUT/f'open-1-{rate}-{i}.json').read_text(encoding='utf-8')) for i in range(1,4)]
        median_run=sorted(runs,key=lambda r:r['summary']['achieved_rps'])[1]
        if median_run['summary']['achieved_rps'] < .95*rate:
            candidates.append((rate,median_run))
    if candidates:
        rate,opened=candidates[0]
        concurrency=max(1,round(opened['summary']['measured_L']))
        run_closed(url,concurrency,10)
        closed=run_closed(url,concurrency,30)
        closed['open_reference']=opened['summary']; closed['rate']=rate
        save('closed.json',closed)
    else:
        save('closed.json',dict(note='Усі три рівні утримано. Прогін перевантаження на 1000 rps для коректного порівняння.'))
        run_open(url,1000,10,a.processes,a.threads)
        overloaded=run_open(url,1000,30,a.processes,a.threads); save('open-extra-1000.json',overloaded)
        if overloaded['summary']['achieved_rps'] < 950:
            concurrency=max(1,round(overloaded['summary']['measured_L']))
            run_closed(url,concurrency,10)
            closed=run_closed(url,concurrency,30); closed['open_reference']=overloaded['summary']; closed['rate']=1000
            save('closed.json',closed)
    cmd(sys.executable,str(ROOT/'scripts/report.py'))
    print('Results and REPORT.md generated. Lab remains running with one web replica.')
if __name__=='__main__': main()
