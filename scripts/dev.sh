#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ ! -d "$ROOT/backend/.venv" ]; then
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -e "$ROOT/backend[dev]"
fi
if [ ! -d "$ROOT/frontend/node_modules" ]; then
  npm --prefix "$ROOT/frontend" install
fi
api_pid=""
cleanup() { if [ -n "$api_pid" ]; then kill "$api_pid" 2>/dev/null || true; fi; }
trap cleanup EXIT
"$ROOT/backend/.venv/bin/uvicorn" pyflow.api:app --reload --app-dir "$ROOT/backend" &
api_pid=$!
npm --prefix "$ROOT/frontend" run dev
