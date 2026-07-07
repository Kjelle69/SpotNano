#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PIDS="$(pgrep -f 'python3 -m uvicorn app.main:app|uvicorn app.main:app' || true)"
if [[ -n "$PIDS" ]]; then
  echo "Stopping uvicorn: $PIDS"
  kill $PIDS 2>/dev/null || true
  sleep 1
  PIDS="$(pgrep -f 'python3 -m uvicorn app.main:app|uvicorn app.main:app' || true)"
  if [[ -n "$PIDS" ]]; then
    echo "Force stopping uvicorn: $PIDS"
    kill -9 $PIDS 2>/dev/null || true
  fi
else
  echo "No uvicorn server running"
fi
