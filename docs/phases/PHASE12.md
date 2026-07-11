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
