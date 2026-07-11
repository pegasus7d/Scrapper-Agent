# Hirable — Project Instructions

This project builds an AI agent (formerly "Scraper Agent" — renamed phase 8,
now covers more than scraping: resume matching, company intelligence, and
application pipeline tracking) that scrapes job postings and interview questions
from public sources. Every doc except this file and `README.md` lives under
`docs/` (moved there phase 8), with every `PHASE{N}.md` further under
`docs/phases/` — `[[docs/Name.md]]` / `[[docs/phases/PHASE{N}.md]]`
throughout this and every other doc is that real path, not an
Obsidian-vault-style bare reference. This file and the two nested
`CLAUDE.md`s (`frontend/`, `backend/scraper/sources/`) stay at their own
directory root on purpose: Claude Code's nested-memory convention
auto-loads `CLAUDE.md` from the directory of any file being read, which
only works if it isn't moved. Full idea/architecture is in [[docs/IDEA.md]]
— read it first for context before making design decisions. The technical
contract (DB models, module layout, API surface, cascade algorithm, test
plan) is in [[docs/DESIGN.md]] — code must follow it, and any deviation
must update [[docs/DESIGN.md]] in the same change.

## Stack
- Python 3.12, env/packages managed with **uv** (`uv venv`, `uv pip install` — never
  plain pip)
- Fetching goes through a `Transport` protocol (`backend/scraper/transport.py`,
  phase 4 amendment — [[docs/phases/PHASE4.md]]), `httpx` default / `scrapling` opt-in. Adding
  or touching a source? See `backend/scraper/sources/`'s own CLAUDE.md for the
  Transport/chunking conventions and the verify-before-proposing rule.
- `pydantic` for extraction schemas / validation
- SQLite for storage (jobs dedupe on the item's permalink, questions on a normalized
  content hash — see DESIGN.md §2)
- LLM cascade: cheap/small model for routine extraction, escalate to a stronger model
  only on validation failure or low confidence
- Frontend: React + Vite + TypeScript strict + Tailwind + shadcn/ui (phase 2
  amendment — rules in DESIGN.md §6). See `frontend/`'s own CLAUDE.md for the
  full frontend stack/conventions.
- **Currently running free-only**: there is no `ANTHROPIC_API_KEY` and that is
  deliberate — everything runs on the local Ollama model. Build the escalation path
  per DESIGN.md (it must work when a key appears later), but never require a key,
  never prompt the user for one, and all smoke tests run local-only.

## Code Quality — non-negotiable

This is the base/foundation code for the project. Everything written here must be easy
for anyone to review and understand. No slop.

- **Small, single-purpose functions.** One function does one thing. If a function needs
  a comment to explain its sections, split it.
- **Clear names over comments.** `fetch_job_page()`, not `get_data()`. Names should make
  most comments unnecessary. Comment only the *why* (a constraint, a gotcha), never the
  *what*.
- **Type hints everywhere.** Every function signature fully typed. Pydantic models for
  all structured data — no passing raw dicts between functions.
- **No dead code, no commented-out code, no TODO piles.** If it's not used, delete it.
- **Explicit error handling.** No bare `except:`. Catch the specific exception, and
  either handle it meaningfully or let it propagate. Scraping fails constantly — failures
  must be visible and logged, never silently swallowed.
- **No magic values.** Timeouts, retry counts, model names, URLs → named constants or a
  config module, not literals scattered through the code.
- **Flat over clever.** Prefer boring, readable code over one-liners, nested
  comprehensions, or clever tricks. A reviewer should understand any function in one pass.
- **Hard file size limit: 300 lines.** No source file may exceed 300 lines. If a file
  approaches the limit, split it by responsibility — don't ask, just split. This is a
  hard rule, not a guideline.
- **Module layout stays clean.** Fetching, extraction, validation, storage each in their
  own module with a small public surface.
- **Every module reviewable standalone.** Someone reading `extractor.py` should not need
  to read `fetcher.py` to understand it — depend on the schemas (the contract), not on
  each other's internals.
- **Docstrings on public functions** — one line saying what it does and what it returns.
  Not essays.

## Testing — mandatory for every flow

- Framework: `pytest`. Every backend module ships with a mirror test file in `tests/`
  (`test_<module>.py`) in the **same change** — code without tests is not done.
- **No network, no LLM, no real scrapling calls in tests.** Fake the `LLMClient`
  protocol with scripted stubs, monkeypatch `fetcher.fetch` with canned pages, run DB
  tests on in-memory SQLite.
- **Failure paths are first-class.** Every error branch (fetch timeout, invalid LLM
  JSON, validation failure, escalation cap, duplicate rows, 409 on concurrent runs)
  has a named test. A module with only happy-path tests is incomplete.
- The per-module flow coverage table lives in [[docs/DESIGN.md]] §7 — keep it in sync when
  adding flows.
- Definition of done for any change: `pytest` green + `mypy` clean + `ruff check` +
  `ruff format --check` pass. (mypy is what makes "type hints everywhere" enforceable
  — ruff alone does not check type correctness.) Any change touching `frontend/`
  additionally requires `npm run build` to pass (strict `tsc` is the frontend's
  type gate).
- **Smoke test at step boundaries.** Unit tests mock all I/O, so they can never prove
  the real integration works. Before a build-order step (`PHASE{N}.md`, current phase
  is [[docs/phases/PHASE11.md]]) is called done, run the new piece once for real (real Ollama, real
  fetch of one page) and say what happened. Failures found here that unit tests
  missed → add the missing unit test.
- **Never round-trip test a migration's upgrade/downgrade against the real `hirable.db`.**
  A real incident (PHASE11.md step 5): testing a migration's downgrade against the live
  dev DB — even one whose own `upgrade()`/`downgrade()` only touched an unrelated table —
  silently corrupted the `job_embeddings` vec0 virtual table's shadow tables. Always
  `cp hirable.db /tmp/scratch.db` first and run the round-trip against that copy via
  `alembic -x db_url=sqlite:////tmp/scratch.db <command>` (`migrations/env.py`'s
  documented override — note the key is `db_url`, not `sqlalchemy.url`). Only ever run a
  single, one-directional `alembic upgrade head` against the real `hirable.db` itself.

## Git workflow — one feature at a time

- Work on exactly **one feature/step at a time** (build order in the current phase's
  `PHASE{N}.md`, indexed from [[docs/DESIGN.md]] §8). Finish it, validate it
  (`pytest` + `ruff` green), then **commit it** before starting
  the next. Never mix two features in one commit.
- **Commits stay very small.** The unit of a commit is the smallest reviewable,
  green-tested change — one module + its test file is a commit; within a build-order
  step, commit each module as it lands rather than the whole step at once. If a diff
  is hard to review in one sitting, it should have been two commits.
- Commit messages: short imperative summary of the one change, e.g.
  `Add extraction cascade with escalation cap`. One line is usually enough.
- Never commit `.env`, `hirable.db`, or generated artifacts — they are gitignored.
- Work directly on `main` — no feature branches while this is a solo project with
  small commits.
- **No new dependencies without a stated reason.** Adding a package to
  `pyproject.toml`/`package.json` requires one sentence in the commit message saying
  why the stdlib or an existing dep can't do it.

## Conventions
- Keep the orchestration loop hand-rolled and simple — no LangChain/CrewAI/AutoGen.
  These add token overhead we don't need for this task.
- Extraction schemas (`JobExtract`, `QuestionExtract` in `schemas.py`) are the contract
  between fetch and storage — validate every LLM extraction against them before saving.
- Adding or touching a source (chunk-text rules, verify-before-proposing,
  rejected-source history)? See `backend/scraper/sources/`'s own CLAUDE.md — it
  covers that ground in full and shouldn't be duplicated here.

## Autonomous build loop

Every phase's build order lives in its own `PHASE{N}.md` file (DESIGN.md §8 is
the index), and is meant to be driven unattended with `/loop`. Reuse this
exact prompt, swapping the phase file and its final step number for the phase
being built:

```
/loop Work on the project at /Users/debayanbiswas/hirable. Each iteration: read CLAUDE.md, DESIGN.md, and PHASE{N}.md, look at git log to see what is already done, then implement ONLY the smallest next unit from PHASE{N}.md's build order. Validate with pytest, mypy, ruff check, ruff format --check, and npm run build for frontend changes; fix until green; then make one small commit. At each step boundary, run the real smoke test described in CLAUDE.md before moving to the next step. Follow every rule in CLAUDE.md strictly. Stop the loop when PHASE{N}.md step M is complete and all checks pass.
```

Used so far: phase 1 ([[docs/phases/PHASE1.md]], stop at step 6 — the MVP), phase 2
([[docs/phases/PHASE2.md]], stop at step 8), phase 3 ([[docs/phases/PHASE3.md]], stop at step 4), phase 4
([[docs/phases/PHASE4.md]], stop at step 4), phase 5 ([[docs/phases/PHASE5.md]], stop at step 7), phase 6
([[docs/phases/PHASE6.md]], stop at step 9 — done), phase 7 ([[docs/phases/PHASE7.md]], stop at
step 8 — done), phase 8 ([[docs/phases/PHASE8.md]], stop at step 10 — done), phase 9
([[docs/phases/PHASE9.md]], stop at step 10 — done), phase 10
([[docs/phases/PHASE10.md]], stop at step 9 — steps 2-9 done, excluding
two real hard stops reached and reported rather than routed around: step
5 never invents real applicant data, step 9's Gmail reply-detection needs
OAuth credentials only the user can grant. The first real application
submission to a real company stays its own separate, explicit checkpoint
— the "submission gate" — not part of this build order at all), phase 11
([[docs/phases/PHASE11.md]], stop at step 9 — done: the full plan →
review → confirm → execute pipeline is built and wired end-to-end,
verified with a real dry-run against two live ATS postings. **The
submission gate has still never been crossed** — no application has
ever been confirmed/submitted; the first real Confirm is the user's own
click in the Applications view, once real applicant data exists to
answer with).
When a new phase's build order
is written, add its (file, final
step) pair here rather than re-deriving the prompt from scratch.
