# Phase 9 — extensibility refactor: company discovery sources

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 9's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]–[[docs/phases/PHASE8.md]]. Requested
directly after a real code-quality check of the codebase (not the `/insights`
usage report, which covers general Claude Code usage patterns across
unrelated projects, not this one): phase 8 added five new company discovery
sources (a16z, Sequoia, Founders Fund, BVP, plus the earlier Wikipedia
source) without reusing the plugin-registry pattern `backend/scraper/
sources/__init__.py` already established for job/question sources. This
phase is pure refactor — no new user-facing features, no new sources — so
every step's "done" bar is: same real behavior, verified via the existing
test suite plus one real smoke test, just less coupled to extend next time.

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

## Deliberately out of scope

**No new discovery sources, no new features.** This phase exists to make
the *next* source (or the next unrelated feature — see the standing
`FEATURES.md` backlog) cheaper to add, not to add one itself. Job/question
sources (`sources/__init__.py`) are explicitly *not* touched here — that
registry is already the pattern being copied, not a thing under repair.

Next: not started — driven by `/loop` once this file is committed on its
own, per WORKFLOW.md rule 3.
