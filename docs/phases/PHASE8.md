# Phase 8 — interactive UI, pipeline tracking, and full company discovery

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 8's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]–[[docs/phases/PHASE7.md]]. Requested directly across
several messages in one conversation, consolidated here before any code
changes (WORKFLOW.md rule 1 — discuss, don't build — plus rule 3, docs
first). Research threads verified before being written down (WORKFLOW.md
rule 2):

- **UI interactivity, requested first / highest priority — includes a real
  unified company page.** Jobs and Questions already open a detail drawer
  on row click (`setSelected`/`cursor-pointer`, `JobDrawer`/
  `QuestionDrawer`); the new Companies view (phase 7 step 8) and the
  Dashboard's stat cards don't have an equivalent — confirmed by grep: no
  `onClick`/`cursor-pointer` on Companies' list rows or on `StatCard`.
  Beyond a bare detail drawer, a `Company` row's real value is tying
  together data that already exists but lives in three disconnected views
  today: its resolved ATS info, its own scraped `Job`s (confirmed real and
  already filterable — `GET /jobs?source=company:{slug}`, exactly what
  phase 7 step 7's smoke test already queried), and any `InterviewQuestion`s
  tagged with its name (`InterviewQuestion.company`, same filterable
  story via `GET /questions?company={name}`) — no new scraping needed,
  this is pure UI composition over real data. "All KPIs clickable,
  everything clickable" — read as: bring Companies and Dashboard up to
  the same interaction pattern already established elsewhere, and let a
  company page be the actual payoff of phase 7's discovery/resolution/
  scraping landing in one place instead of three.
- **Application pipeline tracking — the single highest-value product gap.**
  `Job.starred` (phase 2 step 8) is the only pipeline primitive today, a
  binary bookmark with no status progression — confirmed by reading
  `models.py`: no other job-lifecycle field exists. The tool is a strong
  discovery+search engine but stops right before the part of job-searching
  people actually need help managing (applied → interviewing → offer /
  rejected). A natural extension of the existing boolean, not a new
  system: a real `status` field, new Alembic migration (phase 7 step 1's
  stamp-vs-upgrade pattern). Real design question for the step itself:
  one `status` enum column (simplest, matches every other string-enum
  field already in this schema — `Run.status`, `Run.kind`) versus a small
  history table if per-transition timestamps turn out to matter, not just
  current state — decide once inside the step, written down either way,
  same discipline as every other open question in this file.
- **Filters present everywhere, not just Jobs/Questions — server-side,
  explicitly.** Confirmed real gap by reading the actual route signatures:
  `GET /jobs` takes `company`/`source`/`q`/`starred`/`limit`/`offset`,
  `GET /questions` takes `company`/`round`/`q`/`limit`/`offset` — `GET
  /companies` (phase 7 step 5) takes none of that, no query params at
  all, and the frontend's `Companies.tsx` only does a client-side name
  substring match over whatever the single unpaginated response returned.
  **Decided:** bring Companies to the same filter/pagination shape as
  Jobs/Questions — real backend query params (`ats_provider`, `source`
  once step 6 adds a second discovery source, `q`, `limit`/`offset`) —
  and *remove* the client-side `.filter()` entirely rather than layer a
  server query on top of it; two overlapping filter implementations for
  the same list is its own kind of bug surface (one drifts stale while
  the other gets fixed). Same discipline applies to every filter this
  phase adds, including the new pipeline-status filter on Jobs and any
  `batch`/multi-`source` filtering Companies gains once steps 5-6 land:
  filter state lives in URL query params sent to the backend, never in a
  client-side `.filter()`/`.includes()` over an already-fetched full list.
- **Live run animation, using the SSE plumbing that already exists.**
  `GET /runs/stream` (phase 6 step 6) and `useRunsLive` already push live
  run updates into `RunProgressPanel`, which already has one small
  animation (a pulsing "running" dot). frontend/CLAUDE.md's own rule is
  explicit: **no animation library** — `motion` was dropped in phase 5 step
  4 specifically because a single count-up used it for something a
  hand-rolled `requestAnimationFrame` tween did in ~15 lines
  (`AnimatedNumber.tsx` already does this for stat numbers). Any richer
  "awesome" progress animation stays CSS transitions / hand-rolled tweens,
  reusing `AnimatedNumber`'s pattern rather than adding a dependency.
- **Full YC company coverage, not just the first page.** Phase 7 step 5's
  own real finding: the initial `/companies` fetch only returns 40 cards;
  confirmed today via a real Playwright session that scrolling the same
  page loads more (40 → 120 after 5 scroll+wait cycles) by firing
  background requests to `45bwzj1sgc-dsn.algolia.net` — a **different
  host** than `ycombinator.com`, so `ycombinator.com/robots.txt`'s
  `Disallow: /companies?*` (which only blocks *that* host's query-string
  views) doesn't apply to it. Confirmed the opposite path doesn't work:
  navigating directly to `ycombinator.com/companies?batch=W25` returned 0
  companies — consistent with that exact path being the disallowed one.
  So real full coverage means driving a real scroll session (the existing
  `DynamicFetcher`-backed `ScraplingTransport`, with a scroll action) and
  reading whatever the client renders, never hand-building Algolia query
  URLs to call directly (a real anti-bot key visible in the page's own JS
  bundle is not the same as an authorized API to call standalone). Each
  company card also carries its own YC batch (a real "Batch" filter exists
  in the UI) — worth capturing alongside the name once real full-coverage
  scraping is in place.
- **A second discovery source: Fortune 500 / largest US companies.**
  Verified real before naming it here: Wikipedia's
  `List_of_largest_companies_in_the_United_States_by_revenue` — plain
  server-rendered HTML (confirmed via a bare `curl`, no JS needed), a
  `wikitable` with ~100 real rows (rank, company name + link, industry,
  revenue, employees, headquarters), and `en.wikipedia.org/robots.txt`
  only disallows `/w/` action paths, not `/wiki/` article pages — this
  page is fetchable with the plain `HttpxTransport` every other
  JSON-API-shaped source already uses, no browser rendering needed unlike
  YC. This is the *actual Fortune 500's* nearest real, public,
  scrape-friendly proxy (Fortune's own site paywalls the full list);
  named honestly as "largest US companies by revenue," not literally
  "Fortune 500," unless a real Fortune-published, scrapable list is found
  during the build.
- **Scheduled, unattended company automation.** Currently discovery and
  resolution are both manual button clicks (`POST /companies/discover`,
  `POST /companies/resolve`, phase 7 steps 5-6). The existing
  `schedules` table + `dispatch_due_schedule` periodic Huey task already
  runs unattended per-source jobs/questions scraping. **Decided:** split
  the two things that had gotten conflated. "Is this enabled thing due to
  run" (`enabled`/`every_hours`/`last_run_at`) is genuinely generic —
  reuse `Schedule` as-is, `kind = "companies"`, `source = "yc"` /
  `"fortune500"`, `SchedulesPanel.tsx` extended rather than duplicated.
  "What running it means" is not generic — a `Run` row's shape
  (`pages_fetched`, `items_saved`, `escalations`, `extraction_tier`
  stats) is built around the LLM-extraction pipeline, and forcing
  "discovered 12 companies, resolved 3" through it would mean either a
  misleading row or special-casing most of `execute_run` until reuse
  stops paying for itself. `dispatch_due_schedule` branches on
  `schedule.kind == "companies"` and calls a new, dedicated Huey task
  instead of `create_run` + `run_scrape_task` — no `Run` row for a
  company-automation tick at all. The existing `active_run_exists`
  mutual-exclusion guard (only one scrape `Run` at a time) does not apply
  here either: company discovery/resolution hits different domains
  (`ycombinator.com`, Wikipedia, Greenhouse/Lever) than whatever
  job/question source might be actively scraping, and is far cheaper than
  an LLM-extraction run, so there's no real reason to block it behind an
  active scrape.
- **Persistent logs.** `config.configure_logging()` currently only calls
  `logging.basicConfig` to stderr — real gap once company discovery/
  resolution run unattended via a periodic task with nobody watching a
  terminal: there is currently no record of what happened overnight.
  Python's stdlib `logging.handlers.RotatingFileHandler` needs no new
  dependency; a real bounded size/backup-count needs picking (a home-lab,
  single-user tool, not a service under real log-volume pressure).

## Build order

1. **Companies gets filter parity + a unified detail page (backend +
   frontend).** `GET /companies` gains real query params matching `GET
   /jobs`'s shape — `ats_provider`, `source`, `q`, `limit`/`offset` — and
   the client-side `.filter()` is removed entirely, not layered under.
   Clicking a company row opens a real detail page/drawer: company
   metadata (name, slug, ats_provider, discovered_at, last_checked_at),
   its own scraped jobs (`GET /jobs?source=company:{slug}`, already a
   real, working filter — no new backend needed there), and any interview
   questions tagged with its name (`GET /questions?company={name}`, same
   story) — the real payoff of phase 7's discovery/resolution/scraping
   landing in one place instead of three disconnected views.
   `pytest`/`mypy`/`ruff` gate for the backend query params, `npm run
   build` gate for the frontend; real look in a browser.
   **Done, in two commits.** `repo.list_companies(session, ats_provider=,
   q=, limit=, offset=)` now returns `(items, total)`, the exact shape
   `repo.list_jobs` already uses — every existing caller (tests,
   `discover`/`resolve` route handlers) updated to unpack the tuple.
   Deliberately scoped down from this step's original wording: no
   `source` filter yet, since `Company.source` doesn't exist until step
   6 — adding a filter param for a column that isn't there would be dead
   code. `LimitParam`/`OffsetParam` pulled out of `routes.py` into the
   shared `deps.py` (already home to `SessionDep`) rather than
   duplicated in `routes_companies.py`. `Companies.tsx` gained a
   provider `Select` and `Pagination`, and a new `CompanyDrawer` fetches
   the company's own jobs/questions on open.
   Smoke: real headless-Chromium session against the live app's 40 real
   companies — the name filter narrowed to exactly 1 real match
   ("Airbnb"), the provider filter narrowed to exactly the 3 real
   `lever`-resolved companies (Lever, The Athletic, Meesho), opening
   Airbnb's drawer showed a real scraped job ("Market Manager · France")
   as a working link, zero console errors. One false alarm caught and
   run down rather than assumed: the filter looked completely broken on
   the first pass (`?q=Airbnb` returned all 40 companies unfiltered) —
   traced to a leftover `uvicorn` process from an earlier smoke test
   still serving stale code on `:8000`, not a real bug; confirmed via a
   fresh in-process `TestClient` that the actual code filtered
   correctly, then killed the stale process and re-ran the full smoke
   test clean.
2. **Application pipeline tracking (backend + frontend).** New `status`
   field on `Job` (new Alembic migration, phase 7 step 1's stamp-vs-upgrade
   pattern) — resolve the enum-vs-history-table question from the research
   thread above for real before writing the migration. `JobDrawer` gets a
   status control (existing `Select`/`Button` components, no new UI
   library); `Jobs.tsx`'s filter bar gains a status filter, server-side
   like every other filter this phase touches. Smoke: real status
   transitions through the live API and UI, confirm a job's status
   survives a reload and filters correctly by it.
   **Done, in two commits (backend, frontend).** Resolved: one `status`
   column (`JOB_STATUSES = ("none", "applied", "interviewing", "offer",
   "rejected")`, matching every other status-like field already in this
   schema — `Run.status`, `Run.kind`) plus `status_changed_at`, not a
   history table — kept separate from the pre-existing `starred`
   bookmark on purpose (a starred-but-untouched job and one actually
   applied to are real, distinct states). New migration verified against
   both a scratch DB and a real copy of the populated dev `hirable.db`
   (174 real jobs) — `server_default='none'` turned out to be required,
   not optional: SQLite's `ALTER TABLE ADD COLUMN` rejects a `NOT NULL`
   column with no default against a non-empty table. `POST
   /jobs/{id}/status` validates against `JOB_STATUSES` before writing
   (422 on an unknown value). Adding the route pushed `routes.py` past
   the 300-line cap — split the resume endpoints into a new
   `routes_resume.py` (mirroring `routes_companies.py`'s existing split).
   Real bug caught before shipping, not after: the drawer's status
   control originally called `jobs.reload()` then immediately looked up
   the "refreshed" job in `jobs.data` — `reload()` is async, so that
   lookup always found the stale value. Fixed by having the status
   endpoint's own response (the real updated `Job`) flow directly back
   into the drawer's state, with `reload()` only responsible for
   refreshing the underlying list.
   Smoke: real headless-Chromium session against the live app (174 real
   jobs) — changed a real job's status `none` → `applied`, the drawer
   showed the real `status_changed_at` timestamp immediately (not after
   a manual refresh), the table showed the new status badge, filtering
   by "applied" narrowed to exactly that 1 real job, zero console
   errors.
3. **Dashboard stat cards become clickable (frontend).** Each `StatCard`
   navigates to its matching view on click — needs `onNavigate`/`setView`
   threaded from `App.tsx` into `Dashboard`, the same prop shape
   `CommandPalette` already receives. Real naming collision to resolve
   here, not paper over: the "Companies" stat card currently counts
   *distinct company names among scraped jobs/questions*
   (`repo.compute_stats`'s `companies_union`), not rows in the new
   `companies` discovery table (phase 7) — decide during this step whether
   the card should link to a filtered Jobs view, the new Companies view,
   or whether the stat itself needs a second card/rename so both real
   numbers stay visible and distinct. `npm run build` gate; real look in a
   browser.
   **Done.** Resolved: a second real number, not a rename that loses one.
   `Stats`/`StatsOut` gain `discovered_companies` (one extra `COUNT` in
   `compute_stats`, against the real `companies` table), the existing
   card relabeled "Companies hiring" and kept pointed at Jobs (that's
   where those company names actually live), a new "Discovered
   companies" card added pointing at the Companies view. Confirmed for
   real against live data the two numbers are genuinely different (115
   vs. 40) — not a hypothetical edge case. `StatCard` takes an optional
   `onClick`; Escalation rate stays deliberately non-interactive — no
   filter for extraction tier exists on Jobs/Questions today, so forcing
   a destination would be worse than leaving it inert.
   Smoke: real headless-Chromium session against the live app — clicking
   "Discovered companies" navigated to Companies, clicking "Jobs"
   navigated to Jobs, and Playwright's own strictness (refuses to click
   a disabled element) confirmed the Escalation rate card is genuinely
   non-interactive rather than just visually different, zero console
   errors.
4. **Richer live-run feedback (frontend).** Build on `RunProgressPanel` +
   `useRunsLive`'s existing SSE stream — no animation library (frontend/
   CLAUDE.md), CSS transitions / hand-rolled tweens only, following
   `AnimatedNumber.tsx`'s own precedent. Real look in a browser during an
   actual run (a real company scrape from phase 7 is enough to trigger
   it), confirm it reads as more alive without a layout jank/flicker.
   **Done.** Three real, hand-rolled additions, no dependency: the four
   stat numbers now use `AnimatedNumber` (previously a bare number swap);
   a new `useChangeFlash` hook (`useRef` + `setTimeout`, paired with a
   Tailwind `transition-colors`) briefly highlights a stat right after a
   real change; a live elapsed-time ticker in the header gives constant
   motion even between SSE frames.
   Smoke: real headless-Chromium session watching two real company
   scrapes (Checkr, then The Athletic, both via `POST
   /companies/{id}/scrape`) — the elapsed ticker genuinely counted up
   (13s → 16s across a real wait), and polling the live DOM caught the
   flash-highlight firing at the exact tick `Saved` changed `0` → `1`
   from a genuine SSE-driven update (not simulated — the run's later
   completion was what ended the polling loop). Zero console errors.
5. **Full YC discovery coverage (backend).** Extend `discover_yc_companies`
   (or a new function beside it) to drive a real scroll session via the
   existing `ScraplingTransport`/`DynamicFetcher` instead of one static
   fetch, capturing every company the scroll surfaces plus its batch.
   Decide and document a real stopping condition (fixed scroll count?
   height-unchanged detection?) rather than scrolling forever. `companies`
   table needs a `batch` column (new Alembic migration, following phase
   7 step 1's real stamp-vs-upgrade pattern). Smoke: one real discovery
   run, confirm meaningfully more than 40 real companies land, each with a
   real batch value.
   **Done, in two commits (transport, discovery+model+UI).** Stopping
   condition: a fixed `scroll_count=5` (confirmed real via Scrapling's own
   `page_action` API, not raw Playwright — 40 → 120 companies), not
   height-unchanged detection — simpler, and the real number this site
   surfaces per scroll-cycle is stable enough not to need adaptive
   stopping for a first version. `ScraplingTransport` gained an optional
   `scroll_count` constructor param (default 0, every other current
   caller unaffected) rather than a new transport class. Real markup
   quirk found while extracting `batch`: the pill's own visible `.text`
   is empty (confirmed directly) — the real batch lives in the pill
   link's `href` (`?batch=Summer%202013`), parsed as a query param
   instead. `discover_yc_companies` now returns `DiscoveredCompany(name,
   batch)` instead of bare names; `Company.batch` is null for the 40
   companies discovered before this step landed (correct and honest, not
   backfilled) and set for every new one.
   Smoke: one real discovery run through the live API — `{"discovered":
   80, "total": 120}`, exactly matching this step's own confirmed 40 →
   120 research finding. 80 of the resulting 120 companies have a real
   batch value (the newly-discovered ones; the original 40 correctly
   stayed null), spanning real, distinct YC batches (Summer 2015, Winter
   2016, and more) — not a single hardcoded value. Confirmed in a real
   browser too: filtering to "Mux" showed a real "YC Winter 2016" badge
   on both the row and its drawer, zero console errors.
6. **Fortune 500 / largest-US-companies discovery (backend).** New
   discovery function against the verified Wikipedia table (plain
   `HttpxTransport`, no browser needed), parsing the real `wikitable`
   structure. Needs a way to distinguish a company's discovery origin
   (new `companies.source` column, `"yc"` vs `"fortune500"` — decide
   during this step whether that also becomes the schedule/source key
   from the automation step below). Smoke: one real discovery run,
   confirm real, recognizable company names land (Walmart, Amazon, etc.),
   distinguishable from YC-discovered ones.
   **Done.** Named `"largest_us_companies"`, not `"fortune500"` as
   originally sketched — matches this phase's own commitment to name it
   honestly (Fortune's own list is paywalled; this is the real, public
   proxy). Real structural finding confirmed before writing the parser:
   the page has three `table.wikitable` elements (revenue/employees/
   profits rankings) — the first is the one wanted; each row's company
   name lives in the second `<td>`'s child `<a>` link, not the cell's
   own `.text` (empty on the real markup, the same quirk YC's batch pill
   already taught this codebase). `POST /companies/discover` gained a
   `source` query param (`"yc"`/`"largest_us_companies"`, default `"yc"`
   for backward compatibility) rather than a second endpoint — matches
   how `POST /runs` already dispatches by a `source` discriminator.
   `GET /companies` gained a matching `source` filter (the `source`
   filter param this step's own research thread flagged as depending on
   this step landing). Frontend: a second "Discover largest US
   companies" button, a source filter `Select`, and a source badge on
   every row/drawer.
   Smoke: one real discovery run through the live API —
   `{"discovered": 100, "total": 220}` (120 real YC + 100 real
   largest-US-companies). Confirmed real, recognizable names present
   (Walmart, Amazon, Apple, Alphabet, Berkshire Hathaway — all found),
   correctly distinguishable by `source` (`?source=yc` → 120,
   `?source=largest_us_companies` → 100). Confirmed in a real browser
   too: filtering to "Walmart" showed a real "Largest US companies"
   badge, zero console errors.
7. **Scheduled company automation (backend).** Resolve the two-shapes
   question above for real, wire it in, and expose enable/disable the
   same way existing schedules do (reuse `SchedulesPanel.tsx` or add a
   sibling). Smoke: a real scheduled tick actually discovers/resolves
   without any manual button click, confirmed via `last_checked_at`/company
   count changing between two real ticks.
   **Done, in two commits (backend, frontend), plus a real bug caught
   mid-smoke-test.** Reused `SchedulesPanel.tsx`, not a sibling — same
   enable/disable/every_hours bookkeeping regardless of what a schedule
   dispatches to. New shared `discover_and_save_companies(session,
   source)` in `discovery.py` so the API route and the new
   `run_company_discovery_task` Huey task don't duplicate the per-source
   dispatch (the route handler shrank to one line). `dispatch_due_schedule`
   branches on `schedule.kind == "companies"`, skipping both the
   `active_run_exists` guard and the `Run`-row creation a jobs/questions
   schedule goes through.
   Real bug caught while smoke-testing, not assumed away: the first
   check (`last_run_at` changed) looked like confirmation the tick had
   *finished* — it hadn't. `run_company_discovery_task(schedule.source)`
   is a decorated Huey task; calling it as a plain function **enqueues**
   it (exactly like `run_scrape_task` already does elsewhere in this
   same function), it does not run synchronously — `mark_schedule_run`
   fires right after enqueueing, not after the work completes. Confirmed
   real by polling company counts *after* `last_run_at` had already
   changed and watching genuine progress over the next couple minutes
   (52 → 67 → 81 → 98 → 118 companies checked) — the resolve pass really
   was still running in the background the whole time. No code fix
   needed (this is the same, already-correct async-enqueue pattern
   `run_scrape_task` uses) — the bug was in the smoke test's own
   assumption, corrected before concluding, not swept under the rug.
   Smoke: created a real `kind="companies", source="yc"` schedule
   through the live API against real data (220 real companies, mixed
   YC/largest-US-companies) — a real periodic Huey tick (fires every
   minute on its own) picked it up with zero manual button clicks,
   `last_run_at` changed for real, and polling confirmed the enqueued
   task genuinely ran to completion: 118 companies checked, 22 newly
   resolved to real ATS providers (Bitmovin, Instawork, Human Interest,
   Lattice, GoCardless, and more). Left the real schedule running in the
   dev DB afterward — it's the intended, working feature now, not test
   pollution to clean up.
8. **Persistent logs (backend).** `RotatingFileHandler` added to
   `configure_logging()`, a real log file path (gitignored, alongside
   `hirable.db`/`huey.db`). Smoke: run the app for real, confirm real log
   lines land in the file, confirm rotation config is sane (doesn't grow
   unbounded).
   **Done.** `configure_logging()` in `config.py` adds a
   `RotatingFileHandler` (5 MB × 3 backups, ~20 MB bound — a real bound for
   a single-user home-lab tool, not unbounded growth) alongside the
   existing stderr handler from `logging.basicConfig()`; both guarded by
   the same "root logger already has handlers → no-op" check so it's safe
   to call from `create_app()` more than once. `LOG_FILE = "hirable.log"`
   gitignored next to `hirable.db`/`huey.db`.
   A real, non-mocked test bug was caught and fixed here, not just app
   code: `test_configure_logging_creates_a_real_log_file` failed because
   its fixture cleared `logging.getLogger().handlers` during pytest's
   *setup* phase — but pytest's own logging plugin re-installs a fresh
   `LogCaptureHandler` on the root logger at the start of the *call*
   phase, after setup finishes, silently undoing the fixture's clear
   before the test body ever ran. Root-caused by writing a standalone
   debug script that cleared handlers inline in a test body instead of a
   fixture and comparing behavior directly — confirmed real via printed
   handler lists at each stage, not guessed. Fixed by moving the actual
   `handlers.clear()` call into each test body (right before
   `configure_logging()`), keeping the fixture only for LOG_FILE
   monkeypatching and save/restore of the real root logger state.
   Smoke: killed all stale processes, deleted any existing `hirable.log`,
   started the real app via `uvicorn --factory backend.api.main:create_app`
   fresh. A real `hirable.log` was created immediately on startup and
   genuinely received real log lines — Huey consumer boot messages, its
   periodic scheduler ticks, and Alembic's migration-context checks (27
   real lines after ~3 seconds of live operation, no mocking). Uvicorn's
   own HTTP access/error logs don't appear in the file, because uvicorn
   configures its `uvicorn.access`/`uvicorn.error` loggers with their own
   non-propagating handlers by default — expected framework behavior, not
   a gap in this step (which covers this project's own app-level logging,
   already confirmed working). Rotation config confirmed sane by
   inspection of the configured `maxBytes`/`backupCount` (5 MB × 3 = ~20 MB
   ceiling), not by generating 5 MB of real log traffic, which isn't a
   realistic scenario for this tool's actual usage volume.
9. **VC portfolio pages as further discovery sources (backend).**
   `robots.txt` checked for real on four famous startup-funding VCs before
   naming them here (WORKFLOW.md rule 2): **a16z** — no `robots.txt` at all
   (404), which this project already treats as "no restrictions" (same
   interpretation `fetcher.py`'s `_fetch_robots_lines` already codifies);
   **Sequoia Capital** — real `robots.txt` (redirects to
   `sequoiacap.com/robots.txt`), empty `Disallow:`, wide open; **Founders
   Fund** — empty `Disallow:`, wide open (10s crawl-delay requested,
   honor it as a per-source `delay_s` override, same pattern Arbeitnow
   already uses); **Bessemer Venture Partners** — real disallow list, but
   none of it touches portfolio/company-listing paths. Exact page
   structure/selectors for each are **not yet confirmed** (only
   `robots.txt` has been checked so far) — that's real work for this step
   itself, same as YC's CSS selectors weren't nailed down until phase 7
   step 5's actual build. Reuses the same `companies` table and
   `companies.source` column steps 5-6 already add — one more real value
   each (`"a16z"`, `"sequoia"`, `"foundersfund"`, `"bvp"`), not a new
   table. Smoke: one real discovery run per VC, confirm real portfolio
   company names land, distinguishable by `source`.
   **a16z done** (1/4), in two commits (backend, frontend). Real page
   structure confirmed by fetching the live page before writing any
   parser (WORKFLOW.md rule 2), not assumed from robots.txt alone: unlike
   YC, no scroll/JS-rendering was needed at all — the entire real
   portfolio (849 companies) ships inline as a JS global,
   `window.a16z_portfolio_companies = [...]`, in a `<script>` tag on the
   plain server-rendered page, extracted via regex + `json.loads` and a
   plain `HttpxTransport` (same shortcut class as Wikipedia's source, for
   a different underlying reason). Each element's `title` field (not
   `name`) holds the real company name — confirmed by inspection before
   coding. Added `"a16z"` to `DISCOVERY_SOURCES`, `discover_a16z_companies`
   + `build_a16z_fetcher` to `discovery.py`, a branch in
   `discover_and_save_companies`, and `"a16z"` to the frontend's
   `COMPANY_DISCOVERY_SOURCES` mirror.
   Smoke: real live app, real POST to `/companies/discover?source=a16z`
   against the actual internet (no mocking) — 831 new real companies
   discovered and saved (18 overlapped with existing YC/Wikipedia rows),
   1051 total after. Confirmed genuinely distinguishable by `source`
   (`?source=a16z&q=SpaceX` returns exactly one real row). Confirmed
   idempotent: an immediate second discovery run against the same live
   source found 0 new companies.
   One real false alarm during this smoke test, not a code bug: the first
   attempt hit a stale `uvicorn` process left over from step 8's own smoke
   test, still serving pre-fix code on `:8000` — the exact same trap
   documented in step 1's "Done" note (`pkill -f "uvicorn backend"`
   doesn't match `uvicorn --factory backend...`, since `backend` isn't the
   token immediately after `uvicorn` on that command line). Caught by
   checking `DISCOVERY_SOURCES` directly in a fresh Python process and
   seeing it already included `"a16z"`, which meant the *server process*,
   not the code, was stale. Killed by PID directly, confirmed a truly new
   process before retrying.
   **Sequoia done** (2/4), in two commits plus one real bug fix caught
   mid-smoke-test. A genuinely different real shape from a16z's inline JS
   array: Sequoia's full, accessible company table
   (`table#company_listing`) lives inside a Bootstrap tab-pane hidden by
   default and is itself paginated behind a real "Load More" button, not a
   scroll — confirmed directly (52 companies, alphabetically A-C only,
   before any interaction; 412, A-Z, after clicking the tab open once and
   "Load More" repeatedly). Rather than a Sequoia-specific hack,
   generalized `ScraplingTransport` with `tab_selector`/`load_more_selector`
   params (`_click_load_more`, alongside the existing `_scroll`) — the
   same real dependency-injection discipline as everywhere else in this
   project, since a future VC source may need the same shape again.
   Real bug caught mid-smoke-test, not assumed away: the first live run
   through the actual API found **0** companies despite the direct script
   test right before it finding 412. Root-caused by re-fetching and
   inspecting the actual returned DOM: clicking `#all-tab` triggers a real
   FacetWP AJAX re-render that *replaces* the whole results table —
   sometimes leaving `<tbody class="facetwp-template"></tbody>` genuinely
   empty for a window after the tab click, and a `.facetwp-load-more`
   click during that window either finds nothing or clicks a soon-to-be
   -stale `ElementHandle`, raising a generic Playwright `Error` (not a
   clean timeout) when the AJAX re-render replaces the DOM mid-click. Not
   a one-off flake: a second bare-script repro (bypassing the API) showed
   the same failure at iteration 2. Fixed by waiting for real rows
   (`page.wait_for_selector(...)`) after the tab click instead of a blind
   sleep, and by tolerating up to 3 *consecutive* click errors (retrying
   with a fresh `query_selector` each time, since each failure is a
   transient race with in-flight AJAX, not proof the button is gone) while
   still stopping immediately and correctly when the button is genuinely
   `None` — the real end-of-results signal once the last page has loaded.
   Confirmed fixed with a direct script run (411 companies, A-Z,
   reproducible) before trusting the live API smoke test again.
   Smoke: real live app (a truly fresh process this time, killed by exact
   PID rather than a `pkill` pattern, after the same-shaped stale-process
   trap already documented for step 1/a16z above), real POST to
   `/companies/discover?source=sequoia` against the actual internet — 355
   new real companies discovered and saved, 1406 total after (some
   overlap with a16z/YC/Wikipedia rows already on file, expected).
   Confirmed genuinely distinguishable by `source`
   (`?source=sequoia&q=HubSpot` returns exactly one real row). Confirmed
   idempotent: an immediate second discovery run found 0 new companies.
   **Founders Fund done** (3/4), in two commits. The simplest real shape
   of the four so far: `robots.txt` confirmed wide open (10s crawl-delay
   requested, honored via `PageFetcher(delay_s=10.0)` — the same
   per-source override Arbeitnow already established, not a new concept),
   and the page itself needed no scroll, no click, and no pagination —
   confirmed by grepping the fetched HTML for "load more"/"infinite"/
   "pagination" markers and finding none. The entire real portfolio (62
   companies) is plain server-rendered HTML in one page load; each name
   lives as a direct text node inside `h2.tile-heading span` (confirmed
   directly, no `.text`-returns-empty quirk this time).
   `discovery.py` crossed the 300-line hard cap (CLAUDE.md) once this
   fifth source landed — split into `discovery.py` (orchestrator: YC,
   Wikipedia, `DISCOVERY_SOURCES`, `discover_and_save_companies`) and a
   new `discovery_vc.py` (a16z, Sequoia, Founders Fund — the VC-specific
   sources), matching the file's own natural responsibility boundary
   rather than an arbitrary line-count split.
   Smoke: real live app (fresh process, confirmed by PID), real POST to
   `/companies/discover?source=foundersfund` — 34 new real companies
   discovered and saved, 1440 total after. The other 28 (Stripe, SpaceX,
   Anduril, Airbnb, Palantir, and more) were correctly *not* re-attributed
   — confirmed directly that `Anduril` already existed under `source:
   "a16z"` from an earlier discovery run, and `Company.name` is globally
   unique, so the first source to discover a company keeps that
   attribution — expected, pre-existing dedup behavior, not new to this
   step. Confirmed genuinely distinguishable by `source`. Confirmed
   idempotent: an immediate second discovery run found 0 new companies.
   **Bessemer Venture Partners done (4/4) — step 9 complete.** In two
   commits. Real `robots.txt` confirmed: a real disallow list, but exactly
   as anticipated, none of it touches `/companies`. The simplest of the
   four VC shapes: plain server-rendered HTML, no scroll/click/pagination/
   delay needed at all (confirmed directly — no markers found, no
   crawl-delay requested), 517 real companies in one page load via
   `h3.name a.name`.
   Smoke: real live app (fresh process, confirmed by PID), real POST to
   `/companies/discover?source=bvp` — 480 new real companies discovered
   and saved, 1920 total after. The other 37 (Zapier and more) correctly
   kept their original source attribution — confirmed directly that
   `Zapier` already existed under `source: "yc"` (batch "Summer 2012")
   from an earlier discovery run. Confirmed genuinely distinguishable by
   `source`. Confirmed idempotent: an immediate second run found 0 new
   companies.
   **Step 9 summary**: four real VC portfolio sources landed
   (`"a16z"`, `"sequoia"`, `"foundersfund"`, `"bvp"`), each with a
   genuinely different real page shape confirmed by direct inspection
   before writing any parser (WORKFLOW.md rule 2) — an inline JS array, a
   tab-open-plus-click-through-pagination table, and two plain
   server-rendered pages of differing simplicity. One real transport
   capability was generalized along the way (`ScraplingTransport`'s
   `tab_selector`/`load_more_selector`), and one real, non-obvious AJAX
   race-condition bug was caught and fixed mid-smoke-test (Sequoia) rather
   than papered over. 1920 total companies on file across six discovery
   sources by the end of this step (up from 220 at the start of step 7).
10. **`FEATURES.md` (docs).** A user-facing summary of what the app can
    actually do today, written last and only after steps 1-9 are real —
    describing a feature before it exists is exactly the kind of thing
    this project's docs discipline exists to prevent (DESIGN.md describes
    *what is true now*, never aspirationally). Covers: job/question
    sources and the extraction cascade, hybrid search, scheduling and live
    SSE run tracking, resume upload → derived search positions → search,
    application pipeline tracking, and company discovery/resolution/
    scraping/scheduling across every source landed in this phase. Lives at
    the repo root alongside `README.md`/`IDEA.md`/`DESIGN.md`;
    `README.md`'s existing "Status" paragraph (currently stale — still
    says "phases 1-6 complete") gets trimmed to point at it instead of
    maintaining a second, competing feature list that drifts out of sync
    the same way the Status paragraph already has.
    **Done, in one commit.** `FEATURES.md` written at the repo root,
    covering every real section listed above (source inventory, extraction
    cascade, all six company discovery sources, application pipeline
    tracking, hybrid search, dashboard clickability, persistent logs) —
    each claim checked against this phase's own step write-ups above
    rather than re-derived from memory. `README.md`'s stale "Status"
    paragraph (still said "phases 1-6 complete" with a stale 2-source
    company list) trimmed to a single line pointing at `FEATURES.md`,
    plus a stale "current phase is PHASE7.md" cross-reference in
    `CLAUDE.md` fixed while touching nearby text.
    One real gap found and fixed while writing this doc, not glossed
    over: cross-checking step 9's "Companies" UI against the six real
    backend sources showed the discover buttons and filter dropdown were
    still hardcoded to the original two (`yc`, `largest_us_companies`) —
    a16z/Sequoia/Founders Fund/BVP were fully working in the backend and
    reachable via direct API calls (as every step 9 smoke test above did),
    but never wired into the actual UI. Fixed before writing `FEATURES.md`
    (which claims "company discovery... across every source" as a real,
    present-tense feature): both selects now render from the shared
    `COMPANY_DISCOVERY_SOURCES` constant instead of two hardcoded
    `<SelectItem>`s, and the two separate "Discover YC"/"Discover largest
    US companies" buttons collapsed into one source-select + "Discover
    {label}" button. Pushed `Companies.tsx` over the 300-line cap —
    `CompanyDrawer`/`ProviderBadge`/`sourceLabel` split into their own
    `frontend/src/components/CompanyDrawer.tsx`.
    Smoke: real headless-Chromium session against the live app — opened
    the discovery-source select and confirmed all six real labels appear
    ("YC", "Largest US companies", "a16z", "Sequoia", "Founders Fund",
    "BVP"), selected BVP, clicked "Discover BVP", and confirmed a real
    `POST /companies/discover?source=bvp` request fired and a real
    success toast rendered. Reopened a company drawer after the
    `CompanyDrawer` extraction and confirmed its real "Scraped jobs"/
    "Interview questions" sections still render with zero console errors.
    **Phase 8 complete** — all 10 steps done, every one verified against
    the real, live app rather than unit tests alone.

## Deliberately deferred, not forgotten

**Every other VC beyond the four verified in step 9** — the same
discipline applies to each new one: a real `robots.txt`/structure check
before it's named as a source, not assumed from "it's a famous VC, it's
probably fine." Add incrementally, in their own commits, whenever this
project picks discovery sources back up.
