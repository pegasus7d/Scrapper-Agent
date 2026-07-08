# Scraper Agent — Project Instructions

This project builds an AI agent that scrapes job postings and interview questions
from public sources. Full idea/architecture is in `IDEA.md` — read it first for
context before making design decisions. The technical contract (DB models, module
layout, API surface, cascade algorithm, test plan) is in `DESIGN.md` — code must
follow it, and any deviation must update `DESIGN.md` in the same change.

## Stack
- Python
- `scrapling` for fetching pages (stealthy, adaptive — prefer over raw requests/bs4/Selenium)
- `pydantic` for extraction schemas / validation
- SQLite for storage (dedupe by source URL)
- LLM cascade: cheap/small model for routine extraction, escalate to a stronger model
  only on validation failure or low confidence

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
- Definition of done for any change: `pytest` green + `ruff check` + `ruff format
  --check` pass.

## Git workflow — one feature at a time

- Work on exactly **one feature/step at a time** (build order in `DESIGN.md` §8).
  Finish it, validate it (`pytest` + `ruff` green), then **commit it** before starting
  the next. Never mix two features in one commit.
- Commit messages: short imperative summary of the one feature, e.g.
  `Add extraction cascade with escalation cap`.
- Never commit `.env`, `scraper.db`, or generated artifacts — they are gitignored.

## Conventions
- Keep the orchestration loop hand-rolled and simple — no LangChain/CrewAI/AutoGen.
  These add token overhead we don't need for this task.
- Always feed the LLM cleaned text/markdown from Scrapling, never raw HTML — keeps
  token usage down.
- Extraction schemas (`Job`, `InterviewQuestion`) live centrally and are the contract
  between fetch and storage — validate every LLM extraction against them before saving.
- `apply_url` should store the raw href, not a resolved redirect (avoid extra requests
  per job).
- Build one source end-to-end before generalizing to more sources (see "Build order"
  in IDEA.md).

## Sources
- Prioritize sources without explicit anti-scraping ToS friction (LeetCode Discuss,
  Blind, relevant subreddits, open job boards). Glassdoor/LinkedIn are higher-friction
  (login walls, anti-bot) — deprioritize unless specifically requested.
