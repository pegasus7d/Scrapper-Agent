#!/usr/bin/env bash
# Definition of done (CLAUDE.md): pytest + mypy + ruff check + ruff format
# --check, plus oxlint + prettier --check + npm run build whenever
# frontend/ actually changed. One script instead of 6-7 separate manual
# commands per /loop iteration — meant to be wired as a hook (guardrail),
# not just run by hand.
set -euo pipefail
cd "$(dirname "$0")"

echo "== pytest =="
uv run pytest -q

echo "== mypy =="
uv run mypy backend

echo "== ruff check =="
uv run ruff check backend tests

echo "== ruff format --check =="
uv run ruff format --check backend tests

if git status --porcelain -- frontend/ | grep -q . || git show --name-only HEAD -- frontend/ | grep -q .; then
  echo "== oxlint (frontend changed) =="
  (cd frontend && npm run lint)

  echo "== prettier --check (frontend changed) =="
  (cd frontend && npm run format:check)

  echo "== npm run build (frontend changed) =="
  (cd frontend && npm run build)
fi

echo "ALL CHECKS PASSED"
