# Scraper Agent — Low-Level Design

Read `IDEA.md` first for the product idea. This document is the technical contract:
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

- **Python 3.12+** (system Python on this machine is 3.9 — install via Homebrew or
  `uv`; the project venv must be 3.12+ because the code uses modern typing syntax).
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
  `python-dotenv`, `pytest`, `ruff`. Frontend uses plain `npm` (boring > clever).
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
| posting_url      | str, not null | **unique** — the dedupe key                |
| apply_url        | str, null     | raw href, never a resolved redirect        |
| source           | str, not null | e.g. `"weworkremotely"`                    |
| extraction_tier  | str, not null | `"local"` or `"frontier"` — which model    |
| scraped_at       | datetime      | UTC, set by repo layer                     |
| run_id           | int FK → runs |                                            |

### `interview_questions`
| column           | type          | notes                                      |
|------------------|---------------|--------------------------------------------|
| id               | int PK        |                                            |
| company          | str, not null |                                            |
| role             | str, null     |                                            |
| question         | str, not null |                                            |
| round            | str, null     | e.g. `"phone screen"`, `"onsite"`          |
| source_url       | str, not null | indexed, **not** unique — one thread page  |
|                  |               | can yield many questions                   |
| question_hash    | str, not null | **unique** — sha256(company + question),   |
|                  |               | the dedupe key                             |
| source           | str, not null |                                            |
| extraction_tier  | str, not null |                                            |
| scraped_at       | datetime      |                                            |
| run_id           | int FK → runs |                                            |

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
- `question_hash` = sha256 of `company + question` after lowercasing and collapsing
  all whitespace runs to a single space — otherwise trivial formatting differences
  defeat the dedupe.

**Stale-run recovery:** if the process crashes mid-run, its row stays `"running"`
forever and every new `POST /api/runs` would 409. On app startup, any row with
status `"running"` is marked `"failed"` with error `"interrupted by restart"`.

## 3. Module layout (each file < 300 lines, per CLAUDE.md)

```
backend/
  config.py            # all constants: model names, timeouts, retry counts, caps
  schemas.py           # Pydantic extraction contracts: JobExtract, QuestionExtract
  db/
    models.py          # SQLAlchemy ORM models (the 3 tables)
    repo.py            # save_job, save_question, create_run, finish_run, queries
  llm/
    client.py          # LLMClient protocol + OllamaClient + FrontierClient
  scraper/
    fetcher.py         # fetch(url) -> Page(url, markdown) via scrapling
    prompts.py         # extraction prompt templates (constants — prompts are part
                       # of the contract, never inline f-strings in extractor.py)
    extractor.py       # extract(page, schema) -> validated model | Escalated | Failed
    sources.py         # per-source seed URLs + next-link discovery
    pipeline.py        # run_scrape(kind, source): the loop
  api/
    main.py            # FastAPI app factory, CORS, router mounting
    routes.py          # endpoint handlers (thin — call repo/pipeline, no logic)
frontend/
  (React + Vite + Tailwind app — see §6)
tests/
  (mirrors backend/ one test file per module — see §7)
```

### Key contracts

```python
# schemas.py — what the LLM must produce (separate from DB models on purpose:
# extraction contract and storage schema evolve independently)
class JobExtract(BaseModel):
    title: str
    company: str
    location: str | None
    salary: str | None
    requirements: list[str]
    apply_url: str | None

class QuestionExtract(BaseModel):
    company: str
    role: str | None
    question: str
    round: str | None

# llm/client.py — one protocol, two implementations; extractor depends only on this
class LLMClient(Protocol):
    def complete(self, prompt: str) -> str: ...

# extractor.py — the cascade, expressed as a return type, never exceptions-as-flow
@dataclass
class ExtractResult:
    items: list[BaseModel]        # validated extractions
    tier: Literal["local", "frontier"]

class ExtractionFailed(Exception): ...  # raised only after ALL tiers exhausted
```

### Cascade algorithm (extractor.py)

```
extract(page, schema):
  1. prompt local model with page.markdown + JSON schema of `schema`
  2. parse response as JSON, validate each item against `schema`
  3. valid            → return ExtractResult(items, tier="local")
  4. invalid/empty    → retry local ONCE with the validation errors appended
  5. still invalid    → if run escalation count < MAX_ESCALATIONS_PER_RUN:
                          call frontier model, validate
                          valid → return ExtractResult(items, tier="frontier")
  6. still invalid, or escalation cap hit → raise ExtractionFailed
     (pipeline catches it, records {url, error} on the run row, continues)
```

Constants in `config.py`: `LOCAL_MODEL`, `FRONTIER_MODEL`, `MAX_ESCALATIONS_PER_RUN`,
`FETCH_TIMEOUT_S`, `FETCH_RETRIES`, `MAX_PAGES_PER_RUN`, `REQUEST_DELAY_S`
(politeness delay between fetches), `USER_AGENT`, `API_PORT` (8000),
`CORS_ORIGINS` (`http://localhost:5173` — the Vite dev server).

### Fetcher policy (fetcher.py)

- Identify honestly: send the `USER_AGENT` constant (project name + contact), don't
  spoof a browser unless a source demonstrably requires Scrapling's stealth mode.
- Respect `robots.txt`: check via `urllib.robotparser` (cached per domain); a
  disallowed URL raises `FetchError("disallowed by robots.txt")` and is recorded
  like any other fetch failure.
- Retry once (`FETCH_RETRIES = 1`) with a short backoff on timeout or HTTP 5xx.
  HTTP 429 → back off `4 × REQUEST_DELAY_S` before the retry. Any other non-200,
  or a failed retry → `FetchError`. The pipeline records it and continues.

### Pipeline loop (pipeline.py)

```
run_scrape(kind, source):
  run = repo.create_run(kind, source)
  queue = sources.seed_urls(source)
  seen: set[str] = set()
  while queue and run.pages_fetched < MAX_PAGES_PER_RUN:
      if repo.cancel_requested(run): break     # → status "cancelled"
      url = normalize(queue.pop(0));  skip if url in seen;  seen.add(url)
      page = fetcher.fetch(url)                 # FetchError → record, continue
      result = extractor.extract(page, schema)  # ExtractionFailed → record, continue
      repo.save_items(result.items, run, tier=result.tier)  # dedupes internally
      queue += sources.next_links(page, source)
      sleep(REQUEST_DELAY_S)
  repo.finish_run(run)
```

The loop is synchronous and boring on purpose. A run is triggered from the API and
executed in a background thread (FastAPI `BackgroundTasks`); its progress is readable
from the `runs` row at any time — that is the entire "job status" mechanism, no
Celery/queue infra.

The whole of `run_scrape` is wrapped in one `try/except Exception` (the single
allowed broad catch in the codebase): an unexpected crash marks the run `"failed"`
with the error message instead of leaving a zombie `"running"` row.

### MVP sources (decided — one of each kind)

- **Jobs: Hacker News "Who is hiring?"** monthly thread. Plain server-rendered HTML,
  no login, no anti-bot, explicitly public — and the postings are unstructured free
  text, which is exactly the case that justifies LLM extraction over CSS selectors.
  `sources.py` seeds the current month's thread; next-links = the thread's
  pagination (`&p=2` …).
- **Interview questions: Reddit** (`r/cscareerquestions`, `r/leetcode`) via the
  public `.json` endpoints (append `.json` to any listing/thread URL) — structured
  envelope, free-text posts, no login. LeetCode Discuss and Blind are deferred:
  both are JS-heavy with anti-bot friction, better attempted after the pipeline is
  proven (Scrapling's stealth fetcher exists for exactly that attempt).

## 4. API surface

| method | path                  | purpose                                        |
|--------|-----------------------|------------------------------------------------|
| POST   | `/api/runs`           | start a run: `{kind, source}` → `{run_id}` (409 if a run is already active) |
| POST   | `/api/runs/{id}/cancel` | request cancellation; run stops at the next loop iteration |
| GET    | `/api/runs`           | list runs, newest first                        |
| GET    | `/api/runs/{id}`      | one run incl. live counters + errors           |
| GET    | `/api/jobs`           | list jobs; filters: `company`, `source`, `q` (title search), paginated |
| GET    | `/api/questions`      | list questions; filters: `company`, `round`, `q`, paginated |
| GET    | `/api/stats`          | totals for the dashboard: job count, question count, companies, escalation rate |

All responses are Pydantic response models — no raw dicts out of routes. Errors use
FastAPI's standard `{"detail": ...}` shape. List endpoints paginate with
`?limit=` (default 20, max 100) and `?offset=`, and return `{items, total}`.

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
   is active), "New scrape" button → small modal (kind + source dropdowns).
2. **Jobs** — searchable/filterable table: title, company, location, salary, source,
   scraped date. Row click opens a detail drawer with requirements list + posting /
   apply links.
3. **Questions** — same table pattern: question (truncated), company, role, round.
   Row click → drawer with full question text + source link.

No state library — server data via plain `fetch` + a small `useApi` hook. No component
library — Tailwind only, so the UI code stays reviewable like the backend.

**Frontend testing (MVP):** TypeScript strict mode is the safety net; no unit tests
initially — the UI is thin (fetch → render) and all logic lives behind the tested
API. Revisit if UI-side logic grows.

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
| `test_sources.py`    | seed URLs per source; next-link discovery finds pagination; ignores off-source links |
| `test_pipeline.py`   | happy path saves items + finishes run; `FetchError` on one URL → recorded, loop continues; `ExtractionFailed` → recorded, loop continues; `MAX_PAGES_PER_RUN` stops the loop; visited URLs not re-fetched; cancel requested → loop stops, status `"cancelled"`; no API key → escalation disabled, run completes local-only |
| `test_api.py`        | each endpoint happy path (FastAPI `TestClient`); POST `/api/runs` while active → 409; cancel endpoint sets the flag; filters + pagination on list endpoints (limit cap at 100) |

CI gate (even if "CI" is just a local script at first): `pytest` green + `ruff check`
+ `ruff format --check` before any change is considered done.

## 8. Build order — one feature per step, one commit per step

Workflow rule: each numbered step below is built, validated (`pytest` + `ruff`
green), and **committed on its own** before the next step starts. No mixed commits.

0. Project scaffolding: git init + `.gitignore` (done), Python 3.12 venv,
   `pyproject.toml` with pinned deps + ruff config, `README.md`, empty package layout.
1. `config.py`, `schemas.py`, `db/` + tests — the foundations everything depends on.
2. `llm/client.py`, `extractor.py` + tests — the cascade, proven against a fake LLM.
3. `fetcher.py`, `sources.py` (ONE job source), `pipeline.py` + tests.
4. `api/` + tests.
5. Frontend (dashboard → jobs → questions).
6. Second source type (interview questions) — by now it's just a new entry in
   `sources.py` and a schema, which is the test of whether the design held.
