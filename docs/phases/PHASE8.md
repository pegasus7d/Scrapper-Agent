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
2. **Application pipeline tracking (backend + frontend).** New `status`
   field on `Job` (new Alembic migration, phase 7 step 1's stamp-vs-upgrade
   pattern) — resolve the enum-vs-history-table question from the research
   thread above for real before writing the migration. `JobDrawer` gets a
   status control (existing `Select`/`Button` components, no new UI
   library); `Jobs.tsx`'s filter bar gains a status filter, server-side
   like every other filter this phase touches. Smoke: real status
   transitions through the live API and UI, confirm a job's status
   survives a reload and filters correctly by it.
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
4. **Richer live-run feedback (frontend).** Build on `RunProgressPanel` +
   `useRunsLive`'s existing SSE stream — no animation library (frontend/
   CLAUDE.md), CSS transitions / hand-rolled tweens only, following
   `AnimatedNumber.tsx`'s own precedent. Real look in a browser during an
   actual run (a real company scrape from phase 7 is enough to trigger
   it), confirm it reads as more alive without a layout jank/flicker.
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
6. **Fortune 500 / largest-US-companies discovery (backend).** New
   discovery function against the verified Wikipedia table (plain
   `HttpxTransport`, no browser needed), parsing the real `wikitable`
   structure. Needs a way to distinguish a company's discovery origin
   (new `companies.source` column, `"yc"` vs `"fortune500"` — decide
   during this step whether that also becomes the schedule/source key
   from the automation step below). Smoke: one real discovery run,
   confirm real, recognizable company names land (Walmart, Amazon, etc.),
   distinguishable from YC-discovered ones.
7. **Scheduled company automation (backend).** Resolve the two-shapes
   question above for real, wire it in, and expose enable/disable the
   same way existing schedules do (reuse `SchedulesPanel.tsx` or add a
   sibling). Smoke: a real scheduled tick actually discovers/resolves
   without any manual button click, confirmed via `last_checked_at`/company
   count changing between two real ticks.
8. **Persistent logs (backend).** `RotatingFileHandler` added to
   `configure_logging()`, a real log file path (gitignored, alongside
   `hirable.db`/`huey.db`). Smoke: run the app for real, confirm real log
   lines land in the file, confirm rotation config is sane (doesn't grow
   unbounded).
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

## Deliberately deferred, not forgotten

**Every other VC beyond the four verified above** — the same discipline
applies to each new one: a real `robots.txt`/structure check before it's
named as a source, not assumed from "it's a famous VC, it's probably
fine." Add them incrementally, in their own commits, once step 9 above
proves the pattern for the first four.

Next: not started — driven by `/loop` once this file is committed on its
own, per WORKFLOW.md rule 3.
