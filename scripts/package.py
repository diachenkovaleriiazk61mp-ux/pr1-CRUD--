"""Create a submission archive without secrets, environments or Git metadata."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
ROOT=Path(__file__).resolve().parents[1]
files=['README.md','DESIGN.md','REPORT.md','author.json','app.py','schema.sql','requirements.txt','Dockerfile','.dockerignore','.gitignore','.env.example','docker-compose.yml','nginx.conf','start.ps1']
with ZipFile(ROOT/'PR1_variant7_Diachenko.zip','w',ZIP_DEFLATED) as archive:
    for name in files: archive.write(ROOT/name,name)
    for folder in ('scripts','tests','results'):
        for path in (ROOT/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc',):
                archive.write(path,path.relative_to(ROOT))
print(ROOT/'PR1_variant7_Diachenko.zip')
