# Phase 5 — Huey for scheduling and queueing

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 5's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/PHASE1.md]]–[[docs/PHASE4.md]]. Two things in this codebase
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
4. **Dependency audit, backend and frontend (unrelated to Huey — bundled in
   here at explicit request rather than its own phase).** Same discipline
   that found Scrapling sat unused for HTML-cleaning in phase 4: check every
   dependency's actual usage against its capability, not what it "seems" to
   need. One finding already verified: the frontend production bundle is
   888 KB, over Vite's 500 KB warning threshold; `motion` (used in exactly
   one place — `AnimatedNumber.tsx`'s stat-card count-up) pulls in the full
   `framer-motion/dom` build, including gesture/layout/SVG-path engines this
   app never touches. Its `motion/mini` subpath is *not* a safe swap —
   confirmed by an actual failed build: `animateMini` only animates a DOM
   element/selector, not a plain number, which is exactly what this
   component needs. Replace the one `animate()` call with a hand-rolled
   `requestAnimationFrame` tween (~15 lines, no library) and drop `motion`
   entirely. Then: (a) run a real bundle visualizer against the frontend —
   not just reading import statements, which only show intent, not what
   survives tree-shaking — before concluding anything about `recharts`,
   `@base-ui/react`, `cmdk`, or `lucide-react`; (b) re-check every
   `pyproject.toml` dependency the same way (backend already got this
   treatment once in phase 4 — Scrapling → `Transport` abstraction — so this
   is mainly confirming nothing else backend-side is similarly
   over-provisioned, not expecting a repeat finding). Smoke: `npm run build`
   with the real before/after bundle size stated, plus a real look at the
   dashboard's count-up animation in a browser to confirm it still looks
   right after the hand-rolled replacement. **Done**: measured 888.38 KB →
   827.08 KB (−61.3 KB, −283 modules); verified in a real headless-Chromium
   browser (zero console errors, a live 87→88 stat transition confirmed
   working); backend re-check found nothing. **Not acted on, reported for a
   decision instead**: a real marginal-contribution measurement (temporarily
   removing each library and rebuilding) found `recharts` alone accounts for
   ~351 KB (42% of the remaining 827 KB) for one simple grouped bar chart,
   and `cmdk` accounts for ~49 KB for the command palette — unlike `motion`,
   `recharts` was a deliberate, CLAUDE.md-documented phase 2 choice, not
   silently unused, so swapping or lazy-loading it is a bigger call than
   this audit's scope covers on its own.

5. **Himalayas job source.** Verified before writing this: `himalayas.app`'s
   `robots.txt` is fully open (`Allow: /`), and `GET
   /jobs/api?limit=20&offset=N` is a real public JSON API, no auth, returning
   structured fields (title, company, salary range, location/timezone
   restrictions) — confirmed with a real request, 100k+ jobs in the index.
   New `sources/jobs/himalayas.py`: `next_links` computes the next
   `offset` from the response's own `offset`/`limit`/`totalCount` fields
   (no `links.next` field like Arbeitnow — has to be computed), bounded by
   `MAX_PAGES_PER_RUN` like every source. Smoke: one real scrape confirming
   pagination actually advances and chunks parse.
6. **RemoteJobs.org job source.** Verified: `robots.txt` fully open, `GET
   /api/v1/jobs?category=programming&limit=20&offset=N` is real, no auth,
   structured JSON — confirmed with a real request. Same shape as step 5
   (`sources/jobs/remotejobs.py`, offset-based pagination). Flag to check
   during this step, not assume: its `companyLogo` CDN host is
   `cdn-images.himalayas.app`, suggesting this may share underlying data
   with Himalayas — the existing `posting_url` dedupe should catch true
   duplicates, but confirm actual overlap with a real run before deciding
   whether both sources pull their weight. Smoke: one real scrape.
7. **FAQGURU questions source.** Verified: MIT licensed, 5.1k stars, plain
   markdown files by topic (`javascript.md`, `react.md`, `nodejs.md`, ...)
   under `raw.githubusercontent.com` — same no-`robots.txt`,
   built-for-programmatic-access reasoning as the existing `h5bp` source
   (DESIGN.md §3). Planned to extend `sources/questions/github_questions.py`
   by generalizing `GitHubQuestions` to take `owner_repo`/`branch`/`files`
   instead of hardcoded module constants — **did not do that**, because the
   thing this step said to check turned out to matter: a real fetch showed
   FAQGURU's files open with a table-of-contents preamble, then the real
   content as `### Question` headings followed by prose/code-block answers —
   not `h5bp`'s flat bullet list at all. Reusing `_bullet_chunks` would have
   silently produced zero chunks, so `FaqguruQuestions` got its own
   heading-based parser in the same file instead of a generalized shared one.
   Second real finding, from the smoke test itself: chunking on the full
   question+answer text tanked local-model extraction (1/15 chunks
   extracted) — `QuestionExtract` has no answer field anyway, so `Chunk.text`
   was changed to the bare question only, which measured 12/15 (80%) on the
   same real chunks. Smoke: real fetch + local-model extraction of real
   entries (same as PHASE3.md step 4's original), plus a real run through
   the live API confirming `company: null` rows save correctly with proper
   GitHub blob line-anchor `source_url`s, before cancelling the long-running
   full 280-chunk scan.

**Phase 5 (steps 1–7) is complete** — every step validated and smoke-tested.
Two real bugs surfaced by the required smoke tests, each fixed in its own
commit: step 4's docs entry above was itself missing from this file until
being caught here (the code shipped in commit `322f5b6` but the plan was
never actually written down) — fixed by writing it in now rather than
silently leaving the gap; and step 7's answer-text-in-chunk issue, above.
One decision deliberately deferred rather than made unilaterally: whether to
also address `recharts`'s 351 KB bundle contribution (step 4) — a bigger,
more consequential call than a dependency audit's scope covers alone, since
unlike `motion` it was a deliberate, documented choice.

Explicitly considered and excluded from this phase: LinkedIn, Indeed,
Glassdoor, and Naukri all verified hostile to scraping (LinkedIn's
`robots.txt` states automated access is "strictly prohibited"; Indeed and
Glassdoor disallow exactly the job/interview paths this app would want;
Naukri's edge WAF blocks non-browser User-Agents, which conflicts with this
project's honest-UA policy). Wellfound is Cloudflare-fronted and not fully
verified. Y Combinator's `workatastartup.com` has an open `robots.txt` and a
public job listing page, but stopped short of using its embedded Algolia
search key to probe for an undocumented index name — if pursued later, the
legitimate path is a plain HTML scrape via `ScraplingTransport`, not
reverse-engineering the internal search API. Greenhouse/Lever/Ashby have
real public per-company APIs but need a company-slug list, a different
architecture than any current source — deferred.

Open question, settled in step 1: `run_scrape_task` does open its own
SQLAlchemy session per invocation (`repo.make_engine()` + `Session(engine)`
inside the task body) — confirmed to mirror `run_scheduler_loop`'s old
session-per-cycle pattern exactly, as predicted.

Next: no phase 6 yet — propose next steps and wait to be asked, per
[[docs/WORKFLOW.md]] rule 7.
