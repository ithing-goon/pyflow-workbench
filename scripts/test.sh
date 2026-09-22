#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/backend/.venv/bin/pytest" "$ROOT/backend/tests"
npm --prefix "$ROOT/frontend" test
