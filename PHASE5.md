# Phase 5 — Huey for scheduling and queueing

Read `DESIGN.md` first for the system contract; this file only holds phase 5's
step-by-step build order and rationale. See `WORKFLOW.md` for the recurring
process this and every phase file follows.

Same workflow rules as `PHASE1.md`–`PHASE4.md`. Two things in this codebase
currently hand-roll a problem a task-queue library solves: `scheduler.py`'s
`while True` + `sleep(60)` poll loop, and phase 4's frontend queue-runner
(start → poll `/runs/{id}` → start next, living entirely in the browser's
React state). Verified before writing this (WORKFLOW.md rule 2 — don't
design docs off what "seems" true): `huey` (PyPI, MIT, free) ships
`SqliteHuey`, storing the queue and results in a SQLite file with zero extra
services — no Redis/Valkey, matching this project's SQLite-only,
no-new-infrastructure stack — and `huey.consumer.Consumer` is a real class,
not just a CLI wrapper, that can be instantiated with a `Huey` instance and
started programmatically (`.start()`/`.run()`), so it runs as an in-process
worker thread the same way `run_scheduler_loop`'s daemon thread does today —
no second process to launch. `.then()` pipelines
(`task1.s(args).then(task2, ...)`, enqueued via `huey.enqueue(pipeline)`)
chain tasks so one only starts after the previous finishes — the actual
primitive phase 4's frontend queue-runner hand-rolled with sequential
`await`s. `@huey.periodic_task(crontab(...))` covers fixed, code-defined
cron ticks; it does *not* replace the app's dynamic, user-created
`schedules` table (arbitrary `every_hours` rows added/toggled at runtime via
the UI) — that dispatch logic (DESIGN.md's `due_schedules` query) still has
to run somewhere, so the honest scope is a periodic task that ticks every
minute and does what the poll loop does today, not "Huey eliminates the
schedules table." Considered Celery instead: also free/MIT, but needs a
broker (Redis or the Valkey fork) — real new infrastructure for a single
local user, and built for distributed multi-worker throughput this project
doesn't need. Ruled out for this project's scale.

1. **Wire Huey with zero behavior change (backend).** Add `huey` to
   `pyproject.toml` dependencies (stated reason: replaces two hand-rolled
   subsystems below, per CLAUDE.md's "no new dependencies without a stated
   reason"). New `backend/scraper/tasks.py`: `huey = SqliteHuey("scraper-agent",
   filename="huey.db")` (a sibling file to `scraper.db`, not sharing a
   connection with SQLAlchemy) and `@huey.task() def run_scrape_task(kind,
   source)` wrapping today's `execute_run`/`run_scrape`. Start a
   `huey.consumer.Consumer` on a background thread from `create_app`, same
   lifecycle spot `run_scheduler_loop`'s thread starts today.
   `POST /api/runs` enqueues `run_scrape_task` instead of using FastAPI's
   `BackgroundTasks` — manual and scheduled runs both go through the same
   execution path for the first time. Smoke: one real manual run through the
   API, confirm the Huey consumer actually picks it up and it completes.
2. **Replace `scheduler.py`'s poll loop with a Huey periodic task
   (backend).** `@huey.periodic_task(crontab(minute="*"))` runs the existing
   `due_schedules`/`mark_schedule_run` logic once a minute and enqueues
   `run_scrape_task` for anything due, instead of a hand-rolled thread doing
   the same check. Delete `scheduler.py`'s manual loop
   (`run_due_schedules`/`run_scheduler_loop`) once the periodic task covers
   it. Smoke: create a real schedule with a short interval, confirm it fires
   for real through Huey, not just in a test.
3. **Move the multi-select queue server-side (backend + frontend).** New
   endpoint (e.g. `POST /api/runs/batch`, body: `{kind, sources: [...]}`)
   builds a `.then()` pipeline chaining `run_scrape_task` calls and enqueues
   it once — the queue now survives a browser refresh or closed tab, unlike
   phase 4's frontend-only queue state. `NewScrapeModal`/`Dashboard`'s
   client-side `startQueue`/`pollUntilTerminal` sequencing is deleted in
   favor of one API call; the modal still shows a queue indicator, now
   reading it from the backend rather than driving it. Smoke: a real
   multi-source batch through the live API, confirm sequential execution and
   correct per-run rows, plus a real manual multi-source run through the UI
   like phase 4 step 4's smoke test.

Open question to settle in step 1, not before: whether `run_scrape_task`
needs its own SQLAlchemy session per invocation (the consumer thread can't
share the request-scoped session `execute_run` currently expects) — likely
mirrors how `run_scheduler_loop` already opens its own `Session(engine)` per
cycle today.

Next: not started yet — this is the current phase.
