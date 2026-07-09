# Scraper Agent — Project Instructions

This project builds an AI agent that scrapes job postings and interview questions
from public sources. Full idea/architecture is in `IDEA.md` — read it first for
context before making design decisions. The technical contract (DB models, module
layout, API surface, cascade algorithm, test plan) is in `DESIGN.md` — code must
follow it, and any deviation must update `DESIGN.md` in the same change.

## Stack
- Python 3.12, env/packages managed with **uv** (`uv venv`, `uv pip install` — never
  plain pip)
- Fetching goes through a `Transport` protocol (`backend/scraper/transport.py`,
  phase 4 §11 amendment): `httpx` is the default (every source so far is a plain
  JSON/XML/text API — none need HTML cleaning or stealth), `scrapling` (stealthy,
  adaptive) stays available and real as a per-source opt-in for anything that
  genuinely needs it later. Don't add a source-specific HTTP client outside this
  protocol — that's what it exists to prevent.
- `pydantic` for extraction schemas / validation
- SQLite for storage (jobs dedupe on the item's permalink, questions on a normalized
  content hash — see DESIGN.md §2)
- LLM cascade: cheap/small model for routine extraction, escalate to a stronger model
  only on validation failure or low confidence
- Frontend: React + Vite + TypeScript strict + Tailwind, with **shadcn/ui** primitives
  vendored into `frontend/src/components/ui/`, **motion** for animation, **sonner**
  for toasts, **recharts** for charts (phase 2 amendment — rules in DESIGN.md §6).
  Vendored `components/ui/` files are exempt from the 300-line cap and slop review,
  but everything else in `frontend/src` is held to the same standard as the backend.
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
- The per-module flow coverage table lives in `DESIGN.md` §7 — keep it in sync when
  adding flows.
- Definition of done for any change: `pytest` green + `mypy` clean + `ruff check` +
  `ruff format --check` pass. (mypy is what makes "type hints everywhere" enforceable
  — ruff alone does not check type correctness.) Any change touching `frontend/`
  additionally requires `npm run build` to pass (strict `tsc` is the frontend's
  type gate).
- **Smoke test at step boundaries.** Unit tests mock all I/O, so they can never prove
  the real integration works. Before a `DESIGN.md` §8/§9 build-order step is called
  done, run the new piece once for real (real Ollama, real fetch of one page) and say
  what happened. Failures found here that unit tests missed → add the missing unit test.

## Git workflow — one feature at a time

- Work on exactly **one feature/step at a time** (build order in `DESIGN.md` §8).
  Finish it, validate it (`pytest` + `ruff` green), then **commit it** before starting
  the next. Never mix two features in one commit.
- **Commits stay very small.** The unit of a commit is the smallest reviewable,
  green-tested change — one module + its test file is a commit; within a build-order
  step, commit each module as it lands rather than the whole step at once. If a diff
  is hard to review in one sitting, it should have been two commits.
- Commit messages: short imperative summary of the one change, e.g.
  `Add extraction cascade with escalation cap`. One line is usually enough.
- Never commit `.env`, `scraper.db`, or generated artifacts — they are gitignored.
- Work directly on `main` — no feature branches while this is a solo project with
  small commits.
- **No new dependencies without a stated reason.** Adding a package to
  `pyproject.toml`/`package.json` requires one sentence in the commit message saying
  why the stdlib or an existing dep can't do it.

## Conventions
- Keep the orchestration loop hand-rolled and simple — no LangChain/CrewAI/AutoGen.
  These add token overhead we don't need for this task.
- Always feed the LLM cleaned text/markdown from Scrapling, never raw HTML — keeps
  token usage down.
- Extraction schemas (`JobExtract`, `QuestionExtract` in `schemas.py`) are the contract
  between fetch and storage — validate every LLM extraction against them before saving.
- `apply_url` should store the raw href, not a resolved redirect (avoid extra requests
  per job).
- Build one source end-to-end before generalizing to more sources (build order:
  DESIGN.md §8).

## Sources
- Prioritize sources without explicit anti-scraping ToS friction: open job board
  APIs/RSS feeds (RemoteOK, WeWorkRemotely, Arbeitnow), and permissively-licensed
  curated content (GitHub question banks) over scraping forums at all.
- **Verify before proposing, not after.** Check `robots.txt` and licensing for any
  new source before writing it into DESIGN.md — "seems public" is not verification.
  Three sources were proposed early on the assumption they'd be low-friction and
  turned out not to be once actually checked: **Reddit** (robots.txt disallows all
  crawling — see DESIGN.md §3), **LeetCode Discuss** (robots.txt disallows
  `/graphql` and `/forums`; Discuss is a GraphQL-driven SPA, so even a rendered
  browser fetch pulls data through a channel they've closed to crawlers), and
  **Blind** (blocks even a plain `robots.txt` request with an anti-bot page). Do
  not revisit these without new evidence the policy changed.
- Glassdoor/LinkedIn/Indeed are similarly high-friction (login walls, anti-bot) —
  deprioritize unless specifically requested and re-verified.

## Autonomous build loop

Every build-order section (DESIGN.md §8, §9, §10, ...) is meant to be driven
unattended with `/loop`. Reuse this exact prompt, swapping the section number
and its final step number for the phase being built:

```
/loop Work on the project at /Users/debayanbiswas/scraper-agent. Each iteration: read CLAUDE.md and DESIGN.md, look at git log to see what is already done, then implement ONLY the smallest next unit from the phase N build order in DESIGN.md §N. Validate with pytest, mypy, ruff check, ruff format --check, and npm run build for frontend changes; fix until green; then make one small commit. At each step boundary, run the real smoke test described in CLAUDE.md before moving to the next step. Follow every rule in CLAUDE.md strictly. Stop the loop when §N step M is complete and all checks pass.
```

Used so far: phase 1 (§8, stop at step 6 — the MVP), phase 2 (§9, stop at step
8), phase 3 (§10, stop at step 4), phase 4 (§11, stop at step 4). When a new
phase's build order is written, add its (§N, final step) pair here rather than
re-deriving the prompt from scratch.
