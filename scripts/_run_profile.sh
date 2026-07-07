#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/stop_server.sh"

if command -v fuser >/dev/null 2>&1 && fuser /dev/video0 >/dev/null 2>&1; then
  echo "WARNING: /dev/video0 is busy:"
  fuser -v /dev/video0 || true
fi

echo "Dashboard: http://127.0.0.1:8000"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
