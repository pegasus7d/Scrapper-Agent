# Scraper Agent — Low-Level Design

Read [[IDEA.md]] first for the product idea. This document is the technical contract:
DB models, module layout, API surface, UI plan, and testing strategy. Code that
deviates from this design should update this file in the same change.

## 1. System overview

```
┌──────────────┐     ┌───────────────────────────────────────────┐
│  React UI    │────▶│  FastAPI backend                          │
│  (Vite+TW)   │◀────│                                           │
└──────────────┘     │  api/ ── pipeline/ ── extractor/ ── llm/  │
                     │              │            │               │
                     │           fetcher      cascade            │
                     │          (scrapling) (ollama→frontier)    │
                     │              │                            │
                     │           SQLite (SQLAlchemy 2.0)         │
                     └───────────────────────────────────────────┘
```

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2.0 (typed ORM), Pydantic v2.
- **Frontend:** React + Vite + Tailwind. Light theme, minimal, stylish. Talks to the
  backend over JSON only — no server-rendered pages.
- **DB:** SQLite file (`scraper.db`). Single-writer is fine — scrape runs are
  sequential by design.

### Prerequisites & secrets

- **Python 3.12+** (system Python on this machine is 3.9), with **uv** for all env
  and package management: `uv venv --python 3.12 .venv`, then `uv pip install` —
  never plain pip.
- **Ollama** installed and running, with the local model pulled
  (`ollama pull qwen2.5:7b-instruct`). At run start the pipeline pings Ollama; if
  unreachable, the run fails immediately with a clear error — no silent degradation.
- **`ANTHROPIC_API_KEY`** in the environment for the frontier tier. Loaded from a
  gitignored `.env` file by `config.py` (via `python-dotenv`). **If absent, escalation
  is disabled**: runs still work local-only, escalation attempts are counted as
  failures on the run row, and a warning is logged once at startup. Never hardcode
  or commit secrets.
- **Dependencies** are pinned in `pyproject.toml` (single source of truth — also holds
  the `ruff` config). Core: `fastapi`, `uvicorn`, `sqlalchemy`, `pydantic`,
  `scrapling`, `ollama` (official client for the local tier), `anthropic`,
  `python-dotenv`; dev: `pytest`, `mypy`, `ruff`. Frontend uses plain `npm`
  (boring > clever).
- **README.md** (written in step 0, kept current): setup commands, how to run the
  backend (`uvicorn`), frontend (`npm run dev`), and checks (`pytest`, `ruff`) — a
  new machine should go from clone to running app using only the README.

## 2. Database models

Three tables. `requirements` is stored as a JSON column (SQLite JSON1) — it is
display data, never queried by element, so a join table would be overkill.

### `jobs`
| column           | type          | notes                                      |
|------------------|---------------|--------------------------------------------|
| id               | int PK        | autoincrement                              |
| title            | str, not null |                                            |
| company          | str, not null |                                            |
| location         | str, null     |                                            |
| salary           | str, null     | raw string as posted; no parsing attempt   |
| requirements     | JSON          | list[str]                                  |
| posting_url      | str, not null | **unique** — the dedupe key. The *item's own* permalink (e.g. the HN comment URL), never the listing-page URL — one page yields many jobs, so using the page URL would make every job after the first a false duplicate |
| apply_url        | str, null     | raw href, never a resolved redirect        |
| source           | str, not null | e.g. `"weworkremotely"`                    |
| extraction_tier  | str, not null | `"local"` or `"frontier"` — which model    |
| scraped_at       | datetime      | UTC, set by repo layer                     |
| run_id           | int FK → runs |                                            |
| starred          | bool, default false | user bookmark flag (PHASE2.md step 8)      |

### `interview_questions`
| column           | type          | notes                                      |
|------------------|---------------|--------------------------------------------|
| id               | int PK        |                                            |
| company          | str, **null** | not every question is company-attributed — |
|                  |               | curated GitHub question banks (PHASE3.md) are generic, topic-based, no interview account behind them |
| role             | str, null     |                                            |
| question         | str, not null |                                            |
| round            | str, null     | e.g. `"phone screen"`, `"onsite"`          |
| source_url       | str, not null | indexed, **not** unique — one thread page  |
|                  |               | can yield many questions                   |
| question_hash    | str, not null | **unique** — sha256(company + question),   |
|                  |               | the dedupe key. `company` is normalized to |
|                  |               | `""` when null before hashing              |
| source           | str, not null |                                            |
| extraction_tier  | str, not null |                                            |
| scraped_at       | datetime      |                                            |
| run_id           | int FK → runs |                                            |

### `schedules`  (PHASE2.md step 6)
| column           | type            | notes                                     |
|------------------|-----------------|--------------------------------------------|
| id               | int PK          |                                            |
| kind             | str             | `"jobs"` or `"questions"`                  |
| source           | str             |                                            |
| every_hours      | int             | 1–168 (one week)                           |
| enabled          | bool            | toggle without deleting                    |
| last_run_at      | datetime, null  | null = never run = due immediately         |

### `runs`  (one row per scrape run — observability)
| column           | type          | notes                                      |
|------------------|---------------|--------------------------------------------|
| id               | int PK        |                                            |
| kind             | str           | `"jobs"` or `"questions"`                  |
| source           | str           |                                            |
| status           | str           | `"running"` / `"completed"` / `"failed"` / `"cancelled"` |
| cancel_requested | bool          | set by the cancel endpoint, checked each loop iteration |
| started_at       | datetime      |                                            |
| finished_at      | datetime null |                                            |
| pages_fetched    | int           |                                            |
| items_saved      | int           |                                            |
| items_duplicate  | int           |                                            |
| escalations      | int           | how often the frontier model was needed    |
| errors           | JSON          | list of {url, error} — capped at 100       |

**Dedupe rules:** jobs dedupe on `posting_url`; questions dedupe on `question_hash`.
Duplicates are counted on the run row and skipped silently (logged at DEBUG).

**Normalization before deduping (repo layer, tested):**
- URLs (`posting_url` and the pipeline's `seen` set): strip the fragment and known
  tracking query params (`utm_*`, `ref`, `gclid`, `fbclid`) — otherwise the same job
  reached via two links stores twice.
- `question_hash` = sha256 of `(company or "") + question` after lowercasing and
  collapsing all whitespace runs to a single space — otherwise trivial formatting
  differences defeat the dedupe, and a null company (PHASE3.md step 4) still
  hashes deterministically.

**Stale-run recovery:** if the process crashes mid-run, its row stays `"running"`
forever and every new `POST /api/runs` would 409. On app startup, any row with
status `"running"` is marked `"failed"` with error `"interrupted by restart"`.

## 3. Module layout (each file < 300 lines, per CLAUDE.md)

```
backend/
  config.py            # all constants: model names, timeouts, retry counts, caps
  schemas.py           # Pydantic extraction contracts: JobExtract, QuestionExtract
  db/
    models.py          # SQLAlchemy ORM models (the 4 tables)
    repo/              # persistence, split by responsibility (all re-exported
                       # flat via __init__.py — callers still write repo.foo(...))
      _writes.py       # run lifecycle, dedupe normalization, save_job/save_question
      _queries.py      # paginated lists, filters, export, dashboard stats
      _schedules.py    # schedule CRUD, due_schedules(now)
  llm/
    client.py          # LLMClient protocol + OllamaClient + FrontierClient
  scraper/
    fetcher.py         # PageFetcher: robots.txt, honest UA, retry/backoff policy —
                       # the ONLY module that touches HTTP; every source goes
                       # through this one fetcher, never rolls its own. The actual
                       # request execution is delegated to a Transport (below,
                       # PHASE4.md step 2), so the policy layer never changes
                       # when the transport does.
    transport.py       # Transport protocol + HttpxTransport (default — every
                       # current source is a plain JSON/XML/text API, none need
                       # HTML cleaning or stealth) + ScraplingTransport (opt-in,
                       # for a source that genuinely needs it later)
    prompts.py         # extraction prompt templates (constants — prompts are part
                       # of the contract, never inline f-strings in extractor.py)
    extractor.py       # extract(page, schema) -> validated model | Escalated | Failed
    sources/           # split by domain as of PHASE4.md step 1 — a platform
                       # lives under jobs/ or questions/, never both
      __init__.py      # Source protocol + merges jobs/questions registries into
                       # one SOURCES dict + the seed_urls/next_links/split_items
                       # dispatch functions pipeline.py calls (unchanged surface)
      _base.py         # shared Chunk, clean_html, MIN_CHUNK_CHARS
      jobs/
        __init__.py    # this domain's registry dict
        hn.py          # HN "Who is hiring?" (PHASE1.md)
        remoteok.py    # RemoteOK (PHASE2.md step 7)
        weworkremotely.py # WeWorkRemotely, RSS (PHASE3.md step 2)
        arbeitnow.py   # Arbeitnow, JSON API (PHASE3.md step 3)
        himalayas.py   # Himalayas, JSON API (PHASE5.md step 5)
        remotejobs.py  # RemoteJobs.org, JSON API (PHASE5.md step 6)
      questions/
        __init__.py    # this domain's registry dict
        hn.py          # HN comment search (PHASE2.md step 2)
        github_questions.py # curated question-bank repos: h5bp (PHASE3.md
                       # step 4) and FAQGURU (PHASE5.md step 7), two
                       # different markdown structures, two parsers
    pipeline.py        # run_scrape(kind, source): the loop
    tasks.py           # Huey wiring (PHASE5.md): run_scrape_task,
                       # run_scrape_batch_item + enqueue_batch (step 3),
                       # dispatch_due_schedule periodic task, in-process consumer
  api/
    main.py            # FastAPI app factory, CORS, router mounting, consumer thread
    routes.py          # endpoint handlers (thin — call repo/pipeline, no logic)
    dto.py              # Pydantic request/response models for routes.py
    export.py           # CSV serialization for the export endpoints
frontend/
  (React + Vite + Tailwind + shadcn/ui app — see §6)
tests/
  (mirrors backend/ one test file per module — see §7)
```

See **[[ARCHITECTURE.md]]** for the module-level contracts (`Chunk`, `Source`,
`Transport`, `LLMClient`, `ExtractResult`), the extraction cascade algorithm,
fetcher/transport policy, and the pipeline loop — split out since it was the
largest single chunk of this file and most orientation reading doesn't need
that level of detail.

### MVP sources (decided — one of each kind)

- **Jobs: Hacker News "Who is hiring?"** monthly thread. Plain server-rendered HTML,
  no login, no anti-bot, explicitly public — and the postings are unstructured free
  text, which is exactly the case that justifies LLM extraction over CSS selectors.
  `sources.py` finds the current month's thread via the free Algolia HN API
  (`hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring`); next-links =
  the thread's items endpoint (`hn.algolia.com/api/v1/items/{id}`), which returns the
  whole thread as JSON in one response — no pagination needed. Both endpoints are
  parsed from `Page.raw` (the undecoded body). Chunking: one top-level comment = one
  `Chunk`, with `url` = the comment permalink (`news.ycombinator.com/item?id=…`).
- **Interview questions: HN comments** matching "interview questions", via the same
  open Algolia API (`search_by_date?query="interview questions"&tags=comment`).
  Chunking: one comment hit = one `Chunk`, `url` = the comment permalink. Many
  comments name no company/question — the LLM returns an empty items list for
  those, which the cascade treats as a valid answer.
  *Reddit was the original plan but is not politely scrapable: as of July 2026 its
  robots.txt (www and old subdomains) is `User-agent: * / Disallow: /`, and our
  fetcher respects robots.txt by policy. Revisit only via Reddit's official OAuth
  API.* LeetCode Discuss and Blind stay deferred: both are JS-heavy with anti-bot
  friction, better attempted after the pipeline is proven (Scrapling's stealth
  fetcher exists for exactly that attempt).

## 4. API surface

| method | path                  | purpose                                        |
|--------|-----------------------|------------------------------------------------|
| POST   | `/api/runs`           | start a run: `{kind, source}` → `{run_id}` (409 if a run is already active) |
| POST   | `/api/runs/batch`     | queue multiple sources as one Huey pipeline: `{kind, sources}` → `{queued}` (PHASE5.md step 3; 409 if a run is already active) |
| POST   | `/api/runs/{id}/cancel` | request cancellation; run stops at the next loop iteration |
| GET    | `/api/runs`           | list runs, newest first                        |
| GET    | `/api/runs/{id}`      | one run incl. live counters + errors           |
| GET    | `/api/jobs`           | list jobs; filters: `company`, `source`, `q` (title search), paginated |
| GET    | `/api/questions`      | list questions; filters: `company`, `round`, `q`, paginated |
| GET    | `/api/stats`          | totals for the dashboard: job count, question count, companies, escalation rate |

All responses are Pydantic response models — no raw dicts out of routes. Errors use
FastAPI's standard `{"detail": ...}` shape. List endpoints paginate with
`?limit=` (default 20, max 100) and `?offset=`, and return `{items, total}`.

The API binds to `127.0.0.1` only and has **no auth** — it is a local tool, never
deployed as-is. The frontend keeps hand-written TypeScript types for these
responses in one file (`frontend/src/api/types.ts`), updated whenever a response
model changes.

## 5. LLM tiers

- **Local (default):** Ollama, `qwen2.5:7b-instruct` (constant in config, swappable).
  Handles every extraction first. Free.
- **Frontier (escalation only):** Claude Haiku 4.5 via the Anthropic SDK — cheapest
  capable tier; extraction-on-clean-markdown does not need a bigger model. Capped by
  `MAX_ESCALATIONS_PER_RUN` so a broken source can never run up a bill.

## 6. UI (light, minimal, stylish)

React + Vite + Tailwind, light theme: white/near-white background, one accent color
(indigo), generous whitespace, `Inter` font. Three views in a left sidebar layout:

1. **Dashboard** — stat cards (total jobs, total questions, companies, escalation
   rate), recent runs table with live status (poll `/api/runs` every 3s while a run
   is active), "New scrape" button → small modal (kind + source checkboxes,
   multi-select as of PHASE4.md step 4 — see below).
2. **Jobs** — searchable/filterable table: title, company, location, salary, source,
   scraped date. Row click opens a detail drawer with requirements list + posting /
   apply links.
3. **Questions** — same table pattern: question (truncated), company, role, round.
   Row click → drawer with full question text + source link.

No state library — server data via plain `fetch` + a small `useApi` hook.

**UI stack (amended for phase 2).** The MVP rule was "no component library —
Tailwind only". Phase 2 amends it: **shadcn/ui** primitives are allowed because
they are vendored source in `frontend/src/components/ui/` (reviewable code in the
repo, not a black-box dependency), plus **sonner** for toasts and **recharts** for
dashboard charts. Rules:

- Vendored `components/ui/` files are generated starting points: type-checked and
  buildable, but exempt from the 300-line cap and slop review; edit them only for
  theme integration, keep app logic out of them.
- Animation is seasoning, not sauce: transitions on drawers/dialogs, count-up on
  stat cards, a pulse on the running badge — nothing animates without a reason.
  No animation library — a hand-rolled `requestAnimationFrame` tween replaced
  **motion** in [[PHASE5.md]] step 4 (it pulled in the full `framer-motion/dom`
  build for one count-up).
- Everything else (views, hooks, api client) stays hand-written and reviewable.

Full frontend conventions (stack details, testing, what's exempt from slop
review) live in `frontend/`'s own `CLAUDE.md`, not duplicated here.

**Phase 2 target look:** same light indigo/Inter identity plus a dark mode toggle,
skeleton loaders instead of dashes, toasts for run lifecycle events, proper empty
states with a CTA, a ⌘K command palette (switch views, search jobs), charts for
items-per-run and escalation trend, and a live progress panel for the active run.

**Frontend testing:** TypeScript strict mode is the safety net; no unit tests —
the UI is thin (fetch → render) and all logic lives behind the tested API. Any
change touching `frontend/` must pass `npm run build` (strict `tsc` + Vite build)
as part of the definition of done. Revisit if UI-side logic grows.

**Multi-select scrapes (PHASE4.md step 4).** The backend keeps its existing
one-run-at-a-time invariant (`POST /api/runs` still takes one `{kind, source}`
and 409s while a run is active) — no backend change. The modal's source picker
becomes checkboxes; on submit the frontend queues the selected sources and
runs them one at a time: start a run, poll `/api/runs/{id}` to a terminal
status, then start the next. A small queue indicator ("Scraping 2 of 4:
remoteok…") reuses the existing toast/skeleton patterns, nothing new.

## Logging

Stdlib `logging`, configured once in `config.py`: `%(asctime)s %(levelname)s
%(name)s %(message)s` to stderr, one logger per module (`logging.getLogger(__name__)`).
Levels: INFO = run lifecycle (started/finished, pages, saves); WARNING = recoverable
failures (fetch error, extraction failure, escalation); DEBUG = dedupe skips and
queue growth. Never `print()`.

## Schema management

`Base.metadata.create_all()` at app startup — no Alembic for the MVP. If a table
changes after real data exists, add Alembic then (and note it here). Until then,
deleting `scraper.db` is the migration story.

## 7. Testing strategy — every flow has unit tests

Framework: `pytest`. Hard rules:

- **No network, no LLM, no real scrapling calls in tests.** `LLMClient` is faked with
  a scripted stub; `fetcher.fetch` is monkeypatched with canned `Page` objects; DB
  tests run on in-memory SQLite (`sqlite:///:memory:`).
- **Failure paths are first-class.** Every error branch in the design above has a
  named test — a module without failure tests is incomplete.

Per-module test plan (mirrors `backend/` one-to-one):

| test file            | flows covered                                                |
|----------------------|--------------------------------------------------------------|
| `test_schemas.py`    | valid payloads pass; missing required field fails; wrong types fail |
| `test_repo.py`       | save job; duplicate `posting_url` skipped + counted; duplicate `question_hash` skipped (incl. case/whitespace variants); URL normalization strips tracking params; run lifecycle (create → counters → finish); stale `"running"` rows marked failed on startup; error list capped at 100 |
| `test_extractor.py`  | local succeeds first try; local fails → retry succeeds; retry fails → frontier succeeds (tier recorded); frontier fails → `ExtractionFailed`; escalation cap reached → no frontier call made; malformed JSON from model → treated as invalid, not a crash |
| `test_fetcher.py`    | returns `Page` with markdown; timeout → retry once → `FetchError`; 5xx → retry; 429 → longer backoff; non-200 → `FetchError`; robots.txt disallowed → `FetchError` without fetching |
| `test_sources.py`    | seed URLs per source; `split_items` turns a canned HN page into chunks with comment permalinks; empty/deleted comments skipped; next-link discovery finds pagination; ignores off-source links |
| `test_pipeline.py`   | happy path saves items + finishes run; one page → many chunks → many saved items with distinct `posting_url`s; `ExtractionFailed` on one chunk → recorded, remaining chunks still processed; `FetchError` on one URL → recorded, loop continues; `MAX_PAGES_PER_RUN` stops the loop; visited URLs not re-fetched; cancel requested → loop stops, status `"cancelled"`; no API key → escalation disabled, run completes local-only |
| `test_api.py`        | each endpoint happy path (FastAPI `TestClient`); POST `/api/runs` while active → 409; cancel endpoint sets the flag; filters + pagination on list endpoints (limit cap at 100) |

CI gate (even if "CI" is just a local script at first): `pytest` green + `mypy`
clean + `ruff check` + `ruff format --check` before any change is considered done.
At each build-order step boundary, additionally smoke-test the new piece against
the real world once (see CLAUDE.md "Testing").

The table above is the MVP snapshot; later phases follow the same rule (mirror
one test file per module) without restating it here. When a source module
becomes a `sources/` package (PHASE3.md), its tests mirror into `tests/sources/`.

## 8. Build order

Each phase's step-by-step build order and rationale lives in its own file, so
this document stays the system contract (current state) and doesn't grow
unbounded with build history — the same reasoning that split `repo.py` and
`sources.py` into packages once they grew past the 300-line cap, applied to
docs instead of code:

- **[[PHASE1.md]]** — MVP (done): scaffolding through the second source type.
- **[[PHASE2.md]]** — polish & usefulness (done): dedupe, relevance gate,
  shadcn/ui, dashboard, dark mode, scheduling, RemoteOK, export/bookmarks.
- **[[PHASE3.md]]** — plugin architecture + more platforms (done): `Source`
  protocol/registry, WeWorkRemotely, Arbeitnow, curated GitHub questions.
- **[[PHASE4.md]]** — architecture for scale (done): domain-split sources,
  `Transport` protocol, per-source politeness, multi-select scrape UI.
- **[[PHASE5.md]]** — Huey, dependency audit, and 3 new sources (done):
  replaces `scheduler.py`'s hand-rolled poll loop and the phase 4 frontend
  queue-runner with `SqliteHuey` tasks/pipelines running in-process; drops
  the oversized `motion` dependency; adds Himalayas, RemoteJobs.org, and
  FAQGURU sources.
- **[[PHASE6.md]]** — search, live updates, and cleanup (done):
  schema-constrained local extraction + selectable local model, live run
  updates via SSE, `sqlite-vec` + FTS5 hybrid search, drops `recharts`,
  README rewrite, real bottleneck pass (no code change needed — nothing
  measured slow at current scale).

When starting a new phase: write its build order into a new `PHASE{N}.md`
(copy the header/workflow-rules boilerplate from the latest one), add it to
the list above, and amend the sections above it in *this* file wherever the
new phase changes current state — the numbered list here is an index, not a
changelog. See [[WORKFLOW.md]] for the full discuss → docs → `/loop` → smoke-test
→ report cycle this is part of.

