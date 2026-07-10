# Phase 1 — MVP build order

Read [[docs/DESIGN.md]] first — this file only holds the step-by-step build order and
its rationale; the system contract (DB models, module layout, API surface,
UI plan) lives there and gets amended in place as phases land, not repeated
here. See [[docs/WORKFLOW.md]] for the recurring process this and every later phase
file follows.

Workflow rule: each numbered step below is finished and validated (`pytest` + `mypy`
+ `ruff` green, plus the step-boundary smoke test) before the next step starts.
Within a step, commit each module + its tests as it lands (see [[CLAUDE.md]] "Git
workflow") — never mix two steps in one commit.

0. Project scaffolding: git init + `.gitignore` (done), Python 3.12 venv,
   `pyproject.toml` with pinned deps + ruff config, [[README.md]], empty package layout.
1. `config.py`, `schemas.py`, `db/` + tests — the foundations everything depends on.
2. `llm/client.py`, `extractor.py` + tests — the cascade, proven against a fake LLM.
3. `fetcher.py`, `sources.py` (ONE job source), `pipeline.py` + tests.
4. `api/` + tests.
5. Frontend (dashboard → jobs → questions).
6. Second source type (interview questions) — by now it's just a new entry in
   `sources.py` and a schema, which is the test of whether the design held.

**Phase 1 (steps 0–6) is complete** — every step validated and smoke-tested.

Next: [[docs/PHASE2.md]].
