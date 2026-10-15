#!/usr/bin/env bash
# dev.sh — start the backend (port 8000) and the frontend (port 5173) together for local development.
# Ctrl+C stops both. Run from the repo root: ./dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"

if [ ! -d "$ROOT/backend/.venv" ]; then
  echo "First run: creating the Python virtualenv and installing dependencies..."
  python3 -m venv "$ROOT/backend/.venv"
  "$ROOT/backend/.venv/bin/pip" install -r "$ROOT/backend/requirements.txt"
  "$ROOT/backend/.venv/bin/playwright" install chromium
fi
[ -f "$ROOT/backend/.env" ] || cp "$ROOT/backend/.env.example" "$ROOT/backend/.env"
[ -d "$ROOT/frontend/node_modules" ] || (cd "$ROOT/frontend" && npm install)

# Stop both child processes when this script exits.
trap 'kill 0' EXIT

(cd "$ROOT/backend" && .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd "$ROOT/frontend" && npm run dev) &
wait
