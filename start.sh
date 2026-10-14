#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")"
replicas="${1:-1}"
case "$replicas" in 1|2) ;; *) echo "Usage: sh start.sh [1|2]" >&2; exit 2 ;; esac
if [ ! -f .env ]; then
  python3 - <<'PYCODE'
import secrets
from pathlib import Path
Path('.env').write_text('POSTGRES_PASSWORD='+secrets.token_hex(24)+'\nPOSTGRES_USER=vaccinations\nPOSTGRES_DB=vaccinations\nPORT=18080\n')
PYCODE
fi
docker compose up -d --build --wait --scale "web=$replicas"
