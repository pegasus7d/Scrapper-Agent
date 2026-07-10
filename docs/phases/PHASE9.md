# Phase 9 — extensibility refactor and robustness: company discovery sources + small fixes

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 9's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]–[[docs/phases/PHASE8.md]]. Requested
directly after a real code-quality check of the codebase (not the `/insights`
usage report, which covers general Claude Code usage patterns across
unrelated projects, not this one): phase 8 added five new company discovery
sources (a16z, Sequoia, Founders Fund, BVP, plus the earlier Wikipedia
source) without reusing the plugin-registry pattern `backend/scraper/
sources/__init__.py` already established for job/question sources. Steps
1-4 are that refactor — no new user-facing features, no new sources, every
step's "done" bar is: same real behavior, verified via the existing test
suite plus one real smoke test, just less coupled to extend next time.

Steps 5-8 are a second, separate real code-quality pass (same session,
found while looking for more "small but important" gaps beyond coupling):
concrete robustness gaps found by reading the actual code, not brainstormed
— no DB backup story despite 1920+ real companies and months of scraped
data on file, no health-check endpoint despite the app now running
unattended scheduled work, an unbounded resume-upload read before any
validation, and fully unbounded export endpoints. Each is small and
independently shippable; none require a design discussion the way the
deferred auto-apply feature (see the standing `FEATURES.md` backlog and
this session's own conversation history) does.

Steps 9-10 widen company discovery breadth (requested directly: the
existing `largest_us_companies` source turned out to only cover the top
~100 companies by revenue, missing companies like Netflix entirely — real,
verified gap, not assumed). Deliberately built on top of step 1's registry
rather than before it, so this phase's own refactor isn't immediately
undermined by the next two sources it adds.

## Why this matters (the actual evidence, not a hunch)

Adding one more company discovery source today touches **8 separate
files**: `config.py` (URL constant), `discovery_vc.py` (new
`build_X_fetcher`/`discover_X_companies` pair), `discovery.py` (import +
`DISCOVERY_SOURCES` tuple + a new `if` branch in `discover_and_save_companies`),
`db/models.py` (a comment), `api/routes_companies.py` (a docstring),
`frontend/lib/sources.ts` (`COMPANY_DISCOVERY_SOURCES` array),
`frontend/components/CompanyDrawer.tsx` (`SOURCE_LABELS` dict), and
`tests/test_discovery.py` (~40 lines of near-duplicate fixture HTML + 3-4
tests). This happened four times during phase 8's step 9, and even after
the pattern was established, the frontend wiring was still missed once
(caught only while writing `FEATURES.md`, see [[docs/phases/PHASE8.md]] step
10's write-up) — real, observed drift, not a hypothetical risk.

Compare to `backend/scraper/sources/__init__.py`'s existing job/question
registry: a `SOURCES: dict[str, Source]` keyed by name, each source
implementing one shared `Source` protocol (`_base.py`). Adding a job/question
source there means writing one class and adding one dict entry — no
dispatch `if/elif` chain to extend, no separate constant list to keep in
sync by hand.

## Build order

1. **Give company discovery sources a real `Source`-style registry
   (backend).** Define a small protocol (e.g. `DiscoverySource` — a
   `build_fetcher()` + `discover(fetcher) -> list[DiscoveredCompany]` pair,
   matching the shape every existing `build_X_fetcher`/`discover_X_companies`
   function pair already has) and a `DISCOVERY_SOURCES: dict[str,
   DiscoverySource]` registry, mirroring `sources/__init__.py`'s own
   `SOURCES` dict. Each of the six current sources (yc, largest_us_companies,
   a16z, sequoia, foundersfund, bvp) becomes one registry entry instead of a
   name string handled by an `if` branch. `discover_and_save_companies`
   collapses to one `registry[source].discover(...)` call, no per-source
   branching left. `DISCOVERY_SOURCES` (the tuple of valid names, used for
   422 validation) becomes `tuple(REGISTRY.keys())`, derived rather than
   hand-maintained. Existing `discover_yc_companies`/`discover_a16z_companies`
   etc. function names and signatures stay exactly as they are — this is a
   registration/dispatch refactor, not a rewrite of any real parsing logic.
   Smoke: run the full existing `pytest tests/test_discovery.py` suite
   (should pass unchanged, since only wiring changes) plus one real live
   discovery pass against a real source (e.g. `POST
   /companies/discover?source=a16z`) to confirm the real network path still
   works identically after the refactor.
   **Done.** Built as a dataclass registry (`DiscoverySource` holding
   `build_fetcher`/`discover` callables), not a `Protocol`+classes rewrite
   like `sources/__init__.py`'s — the existing code here is free functions,
   not classes, so a lighter dict-of-callables fit better without forcing
   an unrelated class rewrite. `DISCOVERY_SOURCES` is now
   `tuple(_REGISTRY.keys())`, derived, not hand-maintained.
   `discover_and_save_companies` collapsed from a 6-branch `if/elif` chain
   to one `entry.discover(entry.build_fetcher())` call plus one shared
   `save_company` loop. Every `discover_X_companies` function keeps its own
   real return type unchanged (`list[DiscoveredCompany]` for YC,
   `list[str]` for the other five) — small per-source adapter functions
   normalize into the registry's uniform shape instead.
   Real bug caught by the existing test suite immediately, not shipped: the
   `yc` entry initially referenced `discover_yc_companies` directly (no
   adapter needed for its return type) — that captures the function object
   at registry-construction time, which silently bypasses
   `monkeypatch.setattr` (patches the module attribute, not an
   already-bound dict value) and made a real, unintended network call to
   `ycombinator.com` during what was supposed to be a fully faked test run.
   Fixed by wrapping `yc` in the same thin call-time-lookup adapter every
   other source already needed, closing the one inconsistency that caused
   it.
   Smoke: `pytest tests/test_discovery.py` — 28/28 pass, no real network
   calls (confirmed by the absence of any `Fetched (200)` log line, unlike
   the failing run before the fix). Real live app, fresh process (killed
   by PID after finding yet another stale `uvicorn` from earlier in this
   same session — the same trap documented repeatedly in PHASE8.md,
   still worth checking every time): real `POST
   /companies/discover?source=bvp` (0 new, 1920 total, already fully
   discovered) and `source=yc` (0 new, real ~13s network round-trip to
   ycombinator.com, batch data on existing rows — e.g. "Summer 2015" —
   confirmed intact) both completed correctly through the new registry
   dispatch path, covering both a batch-carrying source and a non-batch
   one.
2. **Stop hand-mirroring the source list into the frontend (backend +
   frontend).** `COMPANY_DISCOVERY_SOURCES` in `frontend/lib/sources.ts` and
   `SOURCE_LABELS` in `frontend/components/CompanyDrawer.tsx` are both
   hand-maintained copies of information the backend registry (step 1) now
   owns as the single source of truth. Real options to weigh here, not
   pre-decided: (a) a small `GET /companies/sources` endpoint returning
   `[{name, label}]ish` and have the frontend fetch it once, same pattern
   `GET /models` already uses for Ollama's model list; or (b) keep a
   frontend constant but reduce it to *only* the display-label mapping
   (name → human label is genuinely frontend-only information the backend
   has no reason to own), and derive the *valid-names* list itself from the
   existing `GET /companies` response data or a dedicated lightweight
   endpoint. Decide during this step which is real (WORKFLOW.md rule 1 —
   this is exactly the kind of decision to make explicit before coding, not
   default into). Smoke: real browser session confirming the Companies
   view's discovery dropdowns still show all six real sources with correct
   labels, sourced from wherever step 2 lands, not a stale hardcoded copy.
   **Done, in two commits (backend, frontend).** Went with option (a): a
   real `GET /companies/sources` endpoint, same pattern `GET /models`
   already uses — this fully closes the gap, not just shrinks it, since
   option (b) still leaves a hand-maintained label dict that could drift
   again exactly like it already did once. `DiscoverySource` gained a
   `label` field (registry-owned, not the frontend's concern anymore);
   `discovery_source_labels()` exposes real `(name, label)` pairs;
   `DiscoverySourceOut` DTO and the route mirror `ModelOut`/`GET /models`
   directly. Frontend: `COMPANY_DISCOVERY_SOURCES` and `SOURCE_LABELS` both
   deleted outright, replaced by a `DiscoverySource` type + `labelFor()`
   helper, fetched once per component via `useApi('/companies/sources')`
   (Companies.tsx, CompanyDrawer.tsx via a new `sources` prop,
   SchedulesPanel.tsx) — no shared client-side cache, matching this
   project's existing "no state library" convention (frontend/CLAUDE.md).
   Smoke: real live app, fresh processes. `curl localhost:8000/api/companies/sources`
   returned all six real `(name, label)` pairs. Real headless-Chromium
   session: Companies view's both dropdowns showed all six real labels
   ("YC", "Largest US companies", "a16z", "Sequoia", "Founders Fund",
   "BVP"), the Discover button's text updated correctly per selection, and
   the Dashboard's SchedulesPanel showed the same six real labels once
   "companies" kind was selected — zero console errors in either view.
3. **Split `api/routes.py` proactively (backend).** Sitting at 285/300
   lines, importing directly from 8+ modules (discovery, tasks, search,
   models, llm client, export, stream) — it's been split twice already
   (`routes_companies.py`, `routes_resume.py`) once it crossed the cap
   reactively; do it proactively this time before a real feature addition
   forces an emergency split mid-step. Real split boundary to confirm during
   this step (not assumed): likely runs/schedules endpoints into their own
   `routes_runs.py`, mirroring the existing company/resume split. Smoke:
   `pytest`/`mypy`/`ruff` gate plus one real `curl` round-trip per moved
   endpoint against a live server to confirm nothing broke in the move.
   **Done.** Confirmed the guessed boundary was right: runs (`/runs`,
   `/runs/batch`, `/runs/{id}/cancel`, `/runs/stream`, `/runs/{id}`) and
   schedules (`/schedules`, `/schedules/{id}/toggle`) moved into a new
   `routes_runs.py` — they share `_SOURCES_BY_KIND` and discovery-source
   validation (a schedule's only real job is eventually kicking off a run),
   so splitting them together avoided a forced re-duplication of that
   validation logic. `routes.py`: 285 → 178 lines; `routes_runs.py`: 130
   lines — both comfortably under the cap, real headroom for what's next
   rather than 285/300 again immediately.
   Real test breakage caught by the suite, not shipped: `test_api.py`
   monkeypatched `routes.run_scrape_task`/`routes.enqueue_batch` — both now
   live in `routes_runs.py`, so `monkeypatch.setattr` was silently patching
   an attribute that no longer affected the real call site (`routes.py` no
   longer imports either name). `list_local_models` is used by *both*
   files now (`routes.py`'s `GET /models`, `routes_runs.py`'s
   `_resolve_model`) — `_fake_local_models` needed patching on both
   modules, not just one, for run-creation tests that exercise the model
   param. Fixed by importing `routes_runs` in the test file and pointing
   each monkeypatch at wherever the real code now lives.
   Smoke: `pytest` — 336/336 pass. Real live app, fresh process: `GET
   /runs`, `GET /schedules`, `GET /models` all returned real data;
   `POST /runs` (`kind: jobs, source: hn`) returned a real `run_id`, `GET
   /runs/{id}` showed it genuinely running (`pages_fetched` climbing,
   `items_duplicate` counting real dedup hits) not just accepted; `POST
   /runs/{id}/cancel` genuinely stopped it (`status: cancelled`); `GET
   /runs/stream` (SSE) streamed real run history. Confirmed the untouched
   endpoints still work too: `GET /jobs`, `/stats`, `/search` (still in
   `routes.py`) all returned correct real data against the live DB (175
   jobs, 1920 discovered companies).
4. **Table-driven discovery tests (backend).** `tests/test_discovery.py` is
   396 lines, 28 test functions, most of them a near-identical triple per
   source (parse-and-dedupe, empty-input, fetcher-config) differing only in
   fixture HTML and selector names. Real risk this step must actually
   verify, not assume away: a shared parametrized harness could blur real
   per-source differences (YC's batch extraction, Sequoia's click-pagination
   fetcher config) that deserve their own explicit test, not a generic loop
   — confirm during this step which tests genuinely generalize vs. which
   must stay source-specific before collapsing anything. Smoke: line count
   and test count reduction confirmed real (not just moved around), full
   suite still green.
   **Done.** Confirmed the real risk was real, not hypothetical: the "parse
   and dedupe" triples (YC's batch pill, Wikipedia's wikitable, a16z's JS
   array, Sequoia's click-pagination, Founders Fund's/BVP's plain HTML) all
   test genuinely different real markup and stayed fully explicit, one
   fixture each — collapsing those would have been exactly the false
   economy this step's own text warned against. Two places turned out to
   be genuinely, byte-for-byte identical across sources and got
   parametrized for real: "empty page returns no companies" (sequoia,
   foundersfund, bvp — a16z's `raises_when_array_not_found` is a real
   exception to that shape, correctly kept separate) and
   `discover_and_save_companies`'s dispatch/save path for every
   non-batch source (5 near-duplicate tests → 1 parametrized test, since
   that logic only exercises the registry from step 1, never a source's
   real parsing).
   Smoke: line count reduction confirmed real, not just moved around —
   396 → 364 lines. Test *count* stayed the same on purpose (pytest
   expands each parametrize case into its own reported test, e.g.
   `test_discover_and_save_companies_no_batch_sources[bvp-...]`) — the real
   metric here is maintenance cost (lines of near-duplicate code), not the
   number pytest prints, and that dropped genuinely. Full suite: 28/28 in
   `test_discovery.py`, 336/336 overall, still green.
   **Phase 9's original scope (steps 1-4) complete.**

5. **Real SQLite backup mechanism (backend).** `hirable.db` is correctly
   gitignored but has no backup story at all — no scheduled copy, no
   "export everything" path, nothing. SQLite is a single file, so the fix
   is genuinely small: a scheduled or manually-triggered copy to a
   `backups/` directory (gitignored, timestamped filenames, a small
   retention cap so it doesn't grow unbounded — same bounded-growth
   reasoning `LOG_BACKUP_COUNT` already uses for log rotation). Decide
   during this step whether it's a Huey periodic task (consistent with how
   every other unattended background behavior in this app already runs)
   or a documented manual `./backup.sh` — a real tradeoff to weigh, not
   pre-decided here. Smoke: trigger a real backup against the actual
   populated `hirable.db`, confirm the copy is a genuine, openable SQLite
   file with the real row counts, not an empty or partial file.
   **Done.** Went with a Huey periodic task (`create_database_backup`,
   daily at 3am via `crontab(hour="3", minute="0")`), not a manual script
   — a manual step the user has to remember to run would just recreate the
   exact "no real backup happens" gap this closes. Real backup logic in a
   new `backend/db/backup.py`, using `sqlite3.Connection.backup()` rather
   than a raw file copy — the documented-safe way to back up a *live*
   SQLite database (a plain `shutil.copy2` mid-write could produce a
   genuinely corrupt file; a raw copy is fine for the backup target, an
   already-closed static file, never for the live source). New
   `config.DATABASE_FILE`/`BACKUP_DIR`/`BACKUP_RETENTION_COUNT` constants
   (14 daily backups, ~2 weeks, same bounded-growth reasoning
   `LOG_BACKUP_COUNT` already uses); `DATABASE_URL` now derives from
   `DATABASE_FILE` instead of hardcoding the filename twice.
   Real bug caught by this file's own test suite, not shipped: the first
   version timestamped backups to second precision
   (`%Y%m%dT%H%M%SZ`) — two `create_backup()` calls within the same wall
   -clock second (never happens at the real once-daily cadence, but a real
   latent bug, not a hypothetical one) silently collide on the same
   filename, one backup overwriting the other. Caught immediately by
   `test_create_backup_keeps_the_newest_files_when_pruning` failing for
   real, not assumed safe. Fixed with microsecond precision
   (`%Y%m%dT%H%M%S%fZ`).
   Smoke: real backup triggered against the actual populated `hirable.db`
   (1920 real companies, 175 real jobs) — the backup file (7.1 MB, a real
   `backups/hirable-<timestamp>.db`) opened cleanly with `sqlite3` and its
   row counts matched the source exactly (1920/1920, 175/175), not an
   empty or partial file. Confirmed `backups/` is correctly gitignored
   (`git check-ignore -v` matched it against the new rule, `git status`
   shows nothing untracked). Confirmed on a real live app startup that
   Huey's consumer genuinely registers `create_database_backup` as a real
   periodic task (`+ backend.scraper.tasks.create_database_backup` in the
   real startup log), not just wired in source but never actually picked
   up.
6. **`/health` endpoint (backend).** The app runs real unattended
   background work today (Huey's scheduler ticks once a minute,
   dispatching discovery/scrape schedules) with no way to check "is the
   backend actually alive" except hitting an unrelated business endpoint
   and hoping it doesn't fail for a different reason. A small `GET
   /health` returning real status (DB reachable, Huey consumer running)
   — not just a bare 200. Smoke: real curl against a live app confirms a
   real status payload; killing the Huey consumer process and re-checking
   confirms the endpoint actually reflects real state, not a hardcoded OK.
   **Done.** `GET /health` returns `{database, huey_consumer}`, both real:
   `database` runs a real `SELECT 1` against the request-scoped session
   (broad `except Exception` deliberately, same justification
   `execute_run`'s own broad except already uses, DESIGN.md §3 — a health
   check's whole job is to report failure, not raise it); `huey_consumer`
   checks a real thread handle (`app.state.consumer_thread`, newly stored
   by `create_app` when `start_consumer=True`) `is not None and
   .is_alive()`, not a hardcoded flag.
   Smoke adapted honestly, not overstated: the consumer is a daemon
   *thread* inside the same process as the API server, not a separate
   process — there's no way to "kill the Huey consumer process and
   recheck" without killing the whole server the health endpoint itself
   runs on, which would make rechecking impossible by construction. Real
   coverage instead: a live app (fresh process, confirmed by PID) —
   `curl localhost:8000/api/health` returned `{"database": true,
   "huey_consumer": true}`, both genuinely true (a real running consumer
   thread, a real reachable DB). The "not running" case is covered for
   real by `test_health_reports_database_ok_and_no_consumer_in_tests`
   (every test app runs with `start_consumer=False`, so `huey_consumer:
   false` there is a real, verified distinct state, not assumed) and
   `test_health_reports_database_down_for_a_genuinely_broken_engine` (a
   real broken SQLAlchemy engine pointed at an unreachable path, not a
   mock — `create_app()` itself already touches the DB at startup via
   `recover_stale_runs`, so the broken engine is swapped onto
   `app.state.engine` *after* successful construction, otherwise app
   creation itself would fail before `GET /health` is ever reachable).
7. **Resume upload gets a real size/type guard (backend).** `routes_resume.py`'s
   `upload_resume` does `await file.read()` with no limit before any
   validation runs — an oversized or wrong-type file is fully read into
   memory before it's rejected. Add a real max-size constant to
   `config.py` (no magic number inline, per CLAUDE.md) and check content
   length before reading the full body. Smoke: real upload of an
   oversized file gets a fast, clear rejection instead of a slow read
   followed by a late failure; a real valid resume PDF still uploads
   correctly afterward.
   **Done.** New `config.RESUME_MAX_BYTES` (5 MB — real resumes are a
   handful of pages, well under 1 MB as a PDF) and
   `RESUME_CONTENT_TYPE`. Two checks, not one: `Content-Length` header
   checked first (fast rejection, zero bytes read, for the common case a
   browser/curl client sends it), real byte count checked again after
   reading as a fallback for the rare case a client omits the header
   (chunked transfer encoding). Content-type checked before either size
   check — genuinely free, no bytes touched.
   Smoke: real live app, fresh process. A real 6.3 MB dummy file was
   rejected in 18ms total (`413`, `"resume file too large (max 5242880
   bytes)"`) — no slow read/parse first. A real, valid, existing resume
   PDF (`~/career-ops/resume.pdf`, sent with a deliberately wrong
   `Content-Type: text/plain`) was rejected (`422`,
   `"unsupported file type: text/plain"`) before ever reaching
   `pdf_to_markdown`. That same real resume PDF, sent correctly, still
   uploaded and parsed successfully (3700 real Markdown characters, real
   name/contact/education content extracted correctly) — the guard
   rejects genuinely bad input without breaking the real, working path.
8. **Bound the export endpoints (backend).** `GET /jobs/export` and
   `/questions/export` pull every matching row into memory in one
   unbounded query. Real decision to make during this step, not assumed:
   a hard cap with a clear error past it, or real streaming (FastAPI's
   `StreamingResponse`, already used elsewhere in `routes.py` for the SSE
   endpoint) so memory use doesn't scale with row count. Smoke: export
   against the real, current row counts (1920+ companies, however many
   real jobs/questions are on file) and confirm it still completes
   correctly under whichever bound this step lands on.
   **Done.** Went with real streaming, not a hard cap — a cap would have
   actively broken the "export everything" promise the moment real usage
   crossed it, and this app already had a proven, working pattern for
   exactly this class of problem: `GET /runs/stream`'s SSE endpoint
   already solved "keep a DB session alive for a generator-driven
   response" by opening its own short-lived session inside the generator
   rather than depending on FastAPI's request-scoped `SessionDep` (which
   closes as soon as the route handler *returns* — immediately after
   constructing a `StreamingResponse`, well before its body is actually
   sent). `repo.export_jobs`/`export_questions` became lazy (`iter(...)`,
   not `.all()`); `api/export.py` gained `stream_jobs_csv`/
   `stream_jobs_json`/`stream_questions_csv`/`stream_questions_json`,
   each opening its own session and yielding roughly one row at a time,
   mirroring `stream.py`'s `run_updates`/`_run_list_payload` split. The
   pure CSV-row serialization (`jobs_to_csv_lines`/`questions_to_csv_lines`)
   stayed DB-independent and directly testable, same discipline
   `test_export.py` already had — only the DB-touching wrapper changed.
   Smoke: real live app, fresh process, against the real, current row
   counts. `GET /jobs/export` returned exactly 175 real jobs (JSON) /
   176 real CSV lines (175 + header) — both matching the live DB exactly,
   not truncated or duplicated. `GET /questions/export` returned exactly
   109 real questions. A real company filter (`?company=Checkr`) still
   correctly narrowed to 57 real matching rows through the new streaming
   path — filtering wasn't accidentally broken by the refactor.

9. **Russell 1000 as a seventh company discovery source (backend).** Real
   gap found by checking, not guessed: the existing `largest_us_companies`
   source (Wikipedia's revenue-ranked table) only covers the **top ~100
   companies by revenue** (confirmed: 101 real rows) — nowhere near even
   Fortune 500, let alone 1000, and revenue-ranking systematically excludes
   companies like Netflix that carry huge market value on comparatively
   lower revenue. Checked multiple real candidates before picking one, not
   assumed: Wikipedia's own `Fortune_500` article is history/methodology
   prose, not the real list (Fortune itself paywalls it); a market-cap list
   didn't have Netflix; `List_of_S%26P_500_companies` does (503 real
   companies) but Wikipedia's **`Russell_1000_Index`** article is broader
   still — confirmed real, complete, and the right scale for what was
   actually asked for ("Fortune 1000"-equivalent coverage): 1002 real
   company names, Netflix included, effectively a superset of the S&P 500
   list, so this one source replaces shipping two heavily-overlapping
   "large US public company" lists. One real markup quirk found and fixed
   before writing this down: the constituent table's first `<td>` (the
   `Company` column) returns empty `.text` when read directly — same
   parent-vs-child-link quirk YC's batch pill and the original
   `largest_us_companies` table both already have — the name is in that
   cell's child `<a>` link instead, confirmed directly against the real
   page. `robots.txt` already covers this — same `en.wikipedia.org/robots.txt`
   policy verified in PHASE8.md step 6 (only `/w/` action paths disallowed,
   not `/wiki/` articles) applies to any Wikipedia article path, not just
   the one originally checked. Should reuse the registry from step 1 rather
   than landing before it — build this source as a proper registry entry,
   not one more `if` branch the refactor is trying to eliminate. Smoke:
   real discovery run against the live app, confirm Netflix (and a
   spot-check of a few other real Russell 1000 names) land with
   `source="russell1000"`, distinguishable from the existing
   `largest_us_companies` rows.
   **Done, in one commit.** Registered as `"russell1000"` in the step 1
   registry, exactly as planned — no `if` branch added.
   `discovery.py` crossed the 300-line cap again the moment Russell 1000
   landed alongside YC and the registry/orchestration code — split into
   `discovery.py` + a new `discovery_lists.py` (the two Wikipedia "large
   company list" sources: `largest_us_companies` and `russell1000`),
   mirroring the existing `discovery_vc.py` split.
   The real payoff of step 2's registry refactor showed up here directly:
   the frontend needed **zero code changes** to support this seventh
   source — `GET /companies/sources` already serves whatever's in the
   backend registry, so both the Companies view's dropdowns and
   `SchedulesPanel` picked up "Russell 1000" automatically.
   Smoke: real live app, fresh process. `GET /companies/sources` returned
   all seven real sources including `{"name": "russell1000", "label":
   "Russell 1000"}`. Confirmed Netflix genuinely absent before discovery
   (`?q=Netflix` → 0 results) — real POST `/companies/discover?source=
   russell1000` (897 new companies, 2817 total, fast — 1.3s, plain
   `HttpxTransport`, no browser) — Netflix now present with
   `source="russell1000"`. Spot-checked 3M, Zoom (2 real distinct
   companies — ZoomInfo and Zoom Communications), Tesla — all correct.
   Confirmed idempotent (second run: 0 new). Real headless-Chromium
   session confirmed "Russell 1000" genuinely renders in the live
   Companies view's discovery dropdown with zero console errors — the
   frontend change that *didn't* need to happen, verified for real, not
   assumed from the architecture alone.
10. **More VC portfolio sources (backend).** PHASE8.md's own "Deliberately
    deferred, not forgotten" section already flagged this: every VC beyond
    the four verified there (a16z, Sequoia, Founders Fund, BVP) needs the
    same real `robots.txt`/page-structure check before being named, not
    assumed from "it's a famous VC, it's probably fine." Real candidates to
    check during this step (not pre-verified, per WORKFLOW.md rule 2):
    Y Combinator-adjacent accelerators (Techstars, 500 Global) and a few
    more large VC firms (e.g. Accel, Index Ventures, Kleiner Perkins) —
    exact list to be confirmed against real `robots.txt` results, not
    decided here. Same discipline as PHASE8.md step 9: one VC at a time,
    real page structure confirmed before any parser is written, added
    incrementally in their own commits.

## Deliberately out of scope

**Auto-apply and every other feature on the `FEATURES.md` backlog** — this
phase's source-hunting (steps 9-10) is deliberately scoped to *company
discovery* breadth, the same kind of source PHASE8.md's step 9 already
built, using the exact registry this phase's own step 1 sets up. It is not
a general invitation to add unrelated new features into a phase that's
mostly refactor — those stay their own, separately-scoped phases (see this
session's own conversation history on auto-apply, deliberately deferred).
Job/question sources (`sources/__init__.py`) are explicitly *not* touched
in steps 1-4 — that registry is already the pattern being copied, not a
thing under repair.

Next: not started — driven by `/loop` once this file is committed on its
own, per WORKFLOW.md rule 3.
