#!/usr/bin/env bash
# Starts the whole app: backend API (port 8000) + frontend dev server (port 5173).
# Ctrl-C stops both. See README.md "Running" for the manual commands.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -d .venv ]; then
  echo "error: no .venv found — run the Setup steps in README.md first" >&2
  exit 1
fi

if ! curl -s -o /dev/null http://127.0.0.1:11434/api/tags; then
  echo "warning: Ollama is not reachable on port 11434 — scrape runs will fail" >&2
  echo "         start it with: ollama serve   (model: ollama pull qwen2.5:7b-instruct)" >&2
fi

if [ ! -d frontend/node_modules ]; then
  echo "installing frontend dependencies (first run)..."
  (cd frontend && npm install)
fi

trap 'kill 0' EXIT INT TERM

.venv/bin/uvicorn --factory backend.api.main:create_app --port 8000 &
(cd frontend && npm run dev) &

echo
echo "backend:  http://127.0.0.1:8000/api/stats"
echo "frontend: http://localhost:5173"
echo "press Ctrl-C to stop both"
wait
