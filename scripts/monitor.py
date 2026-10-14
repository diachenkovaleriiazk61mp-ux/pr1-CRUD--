"""Supplementary resource samples of only this lab's containers during the series."""
import json, subprocess, time, shutil, os
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DOCKER=shutil.which('docker') or str(Path(os.environ.get('LOCALAPPDATA',''))/'Programs/DockerDesktop/resources/bin/docker.exe')
end=time.monotonic()+1200
with (ROOT/'results/resources.jsonl').open('w',encoding='utf-8') as out:
    while time.monotonic()<end and not (ROOT/'results/closed.json').exists():
        p=subprocess.run([DOCKER,'stats','--no-stream','--format','{{json .}}'],capture_output=True,text=True,encoding='utf-8')
        timestamp=datetime.now(timezone.utc).isoformat()
        for line in p.stdout.splitlines():
            row=json.loads(line)
            if row.get('Name','').startswith('vaccinations-pr1-'):
                out.write(json.dumps(dict(timestamp=timestamp,stats=row))+'\n')
        out.flush()
        time.sleep(30)
