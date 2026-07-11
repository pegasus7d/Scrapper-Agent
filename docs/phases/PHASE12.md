# Phase 12 — source health visibility and cached field detection

Read [[docs/DESIGN.md]] first for the system contract; this file only holds
phase 12's step-by-step build order and rationale. See [[docs/WORKFLOW.md]]
for the recurring process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]-[[docs/phases/PHASE11.md]].

## Why this phase exists

Prompted by researching two external agent tools (verified real via
WebFetch, not assumed from names alone, per WORKFLOW.md rule 2):

- **Agent-Reach** (`Panniantong/Agent-Reach`, MIT, Python, 54.9k stars) —
  gives an agent CLI read access to 13+ internet platforms without API
  keys. Login-gated platforms (Twitter/X, Reddit, LinkedIn) work via a
  locally stored browser session.
- **OpenCLI** (`jackwener/opencli`, Apache-2.0, TypeScript/Node, 26.5k
  stars) — turns a site into a deterministic CLI command by recording a
  browser interaction once and replaying it, instead of re-deriving DOM
  structure live every time.

Neither is adopted as a dependency in this phase, for stated reasons:
- Agent-Reach's login-gated LinkedIn access would reverse a decision this
  project already made deliberately: PHASE1.md deprioritized LinkedIn as
  higher legal risk when scraping *anonymously*; scraping it through your
  own authenticated session is a stronger ToS violation, not a weaker one.
- OpenCLI's browser-automation core requires Node.js plus a Chrome
  extension bridge — a second language runtime and a new UI-side
  dependency, for a Python-only backend (CLAUDE.md), with no scraping gap
  it uniquely closes.

What each tool *does* surface is a pattern worth borrowing without the
dependency, matched against a real, confirmed gap in this codebase:

1. Agent-Reach ships a single `doctor` command that reports which of its
   channels currently work. Hirable has 9 job/question sources
   (`backend/scraper/sources/`, the `SOURCES` registry) plus 8 discovery
   sources (`backend/scraper/discovery.py`, `discovery_vc.py`,
   `discovery_lists.py`) and no equivalent — PHASE9.md's own build order
   already found one real instance of a source silently drifting (shipped
   backend-only, missing from the frontend) before anyone noticed by
   inspection rather than by a health signal. Nothing today distinguishes
   "a scheduled run returned zero rows because nothing matched" from "the
   source's site changed shape and every fetch is now failing."
2. OpenCLI's record-once/replay-deterministically model maps directly onto
   `backend/autoapply/filler.py:61` (`detect_fields`), which re-derives a
   Greenhouse/Lever posting's form field selectors via live Playwright
   inspection on *every* application attempt, even repeat attempts against
   the same ATS instance's identically-shaped form.

Phase 12 builds both, standalone, no new runtime dependencies. It also
fixes a real gap found while reviewing the `/loop` template itself (see
step 3): a stuck iteration (same validation check failing repeatedly) has
no defined stop condition today.

## Build order

1. **Sources doctor (backend).** A `check_source_health(source: Source) ->
   SourceHealth` function per registered source: one cheap, low-timeout
   request (HEAD if the source's seed URL supports it, else a short-timeout
   GET) plus a re-check of `robots.txt` disallow rules already enforced at
   scrape time (reuse the existing robots-parsing path — do not
   reimplement it). No LLM call, no full page fetch/extraction — this is a
   liveness probe, not a scrape. Returns `ok` / `blocked` (robots
   disallows) / `unreachable` (network/timeout/non-2xx) plus the checked
   timestamp. New `GET /sources/health` endpoint runs the check across
   every registered job/question/discovery source and returns the list;
   add a small status indicator to the existing Dashboard source list
   (reuse its current layout, no new page). Mock all HTTP in tests
   (monkeypatch `fetcher.fetch`/`Transport`, per CLAUDE.md's no-network
   rule) — one test per health state (ok/blocked/unreachable) plus a test
   that a robots-disallowed source is reported without ever issuing the
   liveness request. Real smoke test: run `GET /sources/health` against
   the live registry and report the real per-source results.

2. **Field-map cache for auto-apply (backend).** New table
   `field_detection_cache` (ats_provider, form_fingerprint, field_map JSON,
   cached_at) — `form_fingerprint` is a hash of the *shape* `detect_fields`
   already returns (field names/types/selectors, not values), so two
   postings on the same ATS instance with an identical form hash to the
   same cache row. `detect_fields` gains a cache-check path: on a fingerprint
   hit, skip live Playwright field detection and reuse the cached selector
   map; then verify every cached selector still resolves on the live page
   before trusting it (an ATS can change its form between visits) — a
   resolution failure invalidates that cache row and falls through to full
   live detection, which then overwrites the stale entry. Never trust a
   cache hit blindly. One Alembic migration (strip vec0/FTS5 autogenerate
   false positives per existing convention). Tests: fresh fingerprint
   (cache miss → live path, row written), matching fingerprint with
   resolvable selectors (cache hit, live detection skipped), matching
   fingerprint with a stale selector (cache hit → resolution failure →
   live fallback → row overwritten). Real smoke test: run the planner
   twice against the same live Greenhouse posting used in PHASE11.md
   step 9's dry-run and confirm the second run hits the cache (log the
   real timing difference, don't assume one).
   **Done.** Landed with one real design correction from the paragraph
   above: `form_fingerprint` (a hash of `detect_fields`' own output) was
   dropped before writing any code — a form's shape can only be known
   *after* running detection, so a fingerprint of that output can never
   be looked up *before* running it, a chicken-and-egg problem the
   original draft missed. Keyed by `(ats_provider, company_id)` instead —
   both known before opening the page, and Greenhouse/Lever forms are
   configured at a company's ATS account level, so every posting from the
   same company shares one real form shape in practice. `field_map` (JSON,
   same precedent `Application.planned_fields` already set) stores
   `dataclasses.asdict(DetectedField)` per field; a cache hit is verified
   by checking every cached selector still resolves on the live page
   (`page.locator(selector).count() > 0`) before being trusted — any
   mismatch falls through to full live `detect_fields` and overwrites the
   row, exactly as planned. New `backend/autoapply/field_cache.py`
   (`get_cached_fields`/`save_cached_fields`/`fields_resolve_on_page`);
   `_detect_real_fields` in `planner.py` gained the cache-check/overwrite
   path (now needs `session`, threaded through from `run_page_planning`).
   One Alembic migration (`9194e5155074`), vec0/FTS5 false positives
   stripped by hand per convention, round-tripped against a scratch copy
   of `hirable.db` per CLAUDE.md's migration-testing rule before the
   real one-directional `upgrade head` against `hirable.db` itself. 8 new
   tests (`test_autoapply_field_cache.py`: DB round-trip, per-company
   isolation, real-page selector resolution against the existing local
   test-form server) plus one new planner-level integration test
   asserting, by real call-count (not just end-state), that a second
   application to the same company reuses the cache — `len(calls) == 1`
   across two real Playwright-driven `plan_application` calls. Real smoke
   test against a genuinely live posting (Checkr/Greenhouse, extending
   PHASE11.md step 9's dry-run companies): a fresh live call against a
   second, never-applied-to Checkr posting (job 89) ran in 43.98s real
   wall time, reached `awaiting_confirmation` with 16 real detected
   fields, and wrote one real `field_detection_cache` row — kept as real,
   legitimate history (application id 3), same precedent PHASE11.md step
   9 set for not deleting real dry-run records. Immediately attempting a
   second live call against a third Checkr posting (job 90) hit a real,
   correct safety control instead of a cache-hit measurement:
   `safety.check_pacing` raised `PacingViolation` ("only 43s since the
   last application, minimum 300s") — the pacing gate built in PHASE10.md
   working exactly as designed, even under a smoke test. Rather than
   bypass a real safety control in the live dev DB just to force a timing
   comparison, the deterministic call-count proof from the local-server
   integration test stands as the primary verification of the caching
   mechanism itself; the live run's contribution is proving the cache
   write path against a genuinely live ATS page. `pytest` (484 passed,
   +8) / `mypy` / `ruff check` / `ruff format --check` all green (no
   frontend change this step). from what was
   written above: no `timestamp` field on `SourceHealth` (a health check
   is always run synchronously, on demand, from `GET /sources/health` —
   the response's own arrival time already tells the caller when it was
   checked, so a stored timestamp would be redundant) and no HEAD-vs-GET
   branching (`PageFetcher.fetch()` is reused wholesale — a HEAD-only
   fast path would mean a second, unproven code path through the
   fetcher, for a probe that's already cheap at one GET per source).
   `robots.txt` handling turned out cleaner than "re-check the disallow
   rules" implied: `fetcher.py`'s existing `FetchError` was split into a
   `RobotsDisallowed(FetchError)` subtype (one-line change at the single
   raise site), so `health.py` tells "blocked" from "unreachable" via
   `except RobotsDisallowed` vs `except FetchError`, not by parsing the
   error message — and every existing `except FetchError` caller
   (`pipeline.py`) is unaffected since it's still a subtype. Discovery
   sources didn't have a natural "seed URL" to probe (each is a full
   `discover()` function, not a `Source` with `seed_urls()`), so
   `DiscoverySource` gained a `seed_url: str` field populated from each
   source's own already-existing `config.*_URL` constant — the same URL
   `discover()` itself fetches first, so the probe can never drift out of
   sync with what a real discovery run hits. Dynamic per-company sources
   (`sources.SOURCES` keys prefixed `company:`) are excluded from the
   probe by design — there can be thousands of them, not fixed
   infrastructure to monitor. Frontend: the status dot landed in
   `NewScrapeModal.tsx`'s existing per-source checkbox list (fetched
   fresh every time the modal opens, hover shows the failure detail) —
   simpler than a Dashboard-level list, which doesn't currently enumerate
   individual sources at all. 8 new backend tests
   (`test_health.py`/`test_api_sources.py`) plus one covering the new
   `RobotsDisallowed` subtype in `test_fetcher.py`; all mock HTTP, no
   network in the suite. Real smoke test: ran a live backend on a scratch
   port (8001, to avoid touching the user's own already-running dev
   server on 8000) and hit `GET /sources/health` for real — all 17
   registered sources (9 job/question + 8 discovery) reported `ok`
   against real live requests to their real domains. `pytest` (476
   passed, +8) / `mypy` / `ruff check` / `ruff format --check` / `npm run
   build` all green.

3. **Loop-template hardening (docs only, `CLAUDE.md`).** Three additions to
   the reusable `/loop` prompt in the "Autonomous build loop" section,
   closing gaps found by re-reading the template against how phases 10-11
   actually ran:
   - A circuit breaker: if the same validation check (`pytest`/`mypy`/
     `ruff`/`npm run build`) fails on three consecutive attempts at the
     same step, stop the loop and report the failure instead of continuing
     to iterate.
   - An explicit no-fabrication clause: if the next unbuilt step requires
     data, credentials, or an irreversible action only the user can supply
     (the pattern PHASE10.md/PHASE11.md already hit twice — real applicant
     data, Gmail OAuth), stop and report rather than inventing a
     placeholder or routing around it. This was already true in practice
     (both hard stops were honored) but was never actually written into
     the prompt driving the behavior — make it literal instead of relying
     on CLAUDE.md being re-read and correctly inferred each iteration.
   - Require each completed build-order step to get a "Done." writeup
     appended to `PHASE{N}.md` in the same commit (what actually happened,
     real numbers/counts, any bug found) — this happened consistently by
     habit across phases 10-11 but was never a stated requirement.
   No code changes in this step; verify by re-reading the amended template
   against this exact phase's own step 1/2 execution once they're done, and
   note in this file whether the template as written would have produced
   the same behavior.

4. **ToS review spike for Agent-Reach-style authenticated access (research
   only, no code).** Re-run the phase-1/phase-5 source rejection list
   (LinkedIn, Reddit's non-public endpoints, Blind) against the question
   "does scraping this through the user's own authenticated session change
   the ToS/legal calculus versus scraping it anonymously" — record the
   answer per platform in this file. Expected outcome for LinkedIn
   specifically: no change, still rejected — authenticating makes it a
   personal-account ToS violation on top of the existing legal-risk
   rejection, not a mitigation of it. This step exists to make that
   reasoning explicit and checked rather than assumed, per WORKFLOW.md
   rule 2.

Next: driven by `/loop` per [[docs/WORKFLOW.md]] once the user approves
this phase; stop at step 4.
