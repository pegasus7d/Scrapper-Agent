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
| starred          | bool, default false | user bookmark flag (DESIGN.md §9 step 8) |

### `interview_questions`
| column           | type          | notes                                      |
|------------------|---------------|--------------------------------------------|
| id               | int PK        |                                            |
| company          | str, **null** | not every question is company-attributed — |
|                  |               | curated GitHub question banks (§10) are generic, topic-based, no interview account behind them |
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

### `schedules`  (DESIGN.md §9 step 6)
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
  differences defeat the dedupe, and a null company (§10 step 4) still hashes
  deterministically.

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
                       # phase 4 §11 step 2), so the policy layer never changes
                       # when the transport does.
    transport.py       # Transport protocol + HttpxTransport (default — every
                       # current source is a plain JSON/XML/text API, none need
                       # HTML cleaning or stealth) + ScraplingTransport (opt-in,
                       # for a source that genuinely needs it later)
    prompts.py         # extraction prompt templates (constants — prompts are part
                       # of the contract, never inline f-strings in extractor.py)
    extractor.py       # extract(page, schema) -> validated model | Escalated | Failed
    sources/           # split by domain as of phase 4 §11 step 1 — a platform
                       # lives under jobs/ or questions/, never both
      __init__.py      # Source protocol + merges jobs/questions registries into
                       # one SOURCES dict + the seed_urls/next_links/split_items
                       # dispatch functions pipeline.py calls (unchanged surface)
      _base.py         # shared Chunk, clean_html, MIN_CHUNK_CHARS
      jobs/
        __init__.py    # this domain's registry dict
        hn.py          # HN "Who is hiring?" (phase 1 §8)
        remoteok.py    # RemoteOK (phase 2 §9 step 7)
        weworkremotely.py # WeWorkRemotely, RSS (phase 3 §10 step 2)
        arbeitnow.py   # Arbeitnow, JSON API (phase 3 §10 step 3)
      questions/
        __init__.py    # this domain's registry dict
        hn.py          # HN comment search (phase 2 §9 step 2)
        github_questions.py # curated question-bank repos (phase 3 §10 step 4)
    pipeline.py        # run_scrape(kind, source): the loop
    scheduler.py        # background poll loop that starts due schedules
  api/
    main.py            # FastAPI app factory, CORS, router mounting, scheduler thread
    routes.py          # endpoint handlers (thin — call repo/pipeline, no logic)
    dto.py              # Pydantic request/response models for routes.py
    export.py           # CSV serialization for the export endpoints
frontend/
  (React + Vite + Tailwind + shadcn/ui app — see §6)
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
    company: str | None  # None for generic, non-company-attributed question banks
    role: str | None
    question: str
    round: str | None

# sources/__init__.py — a page is split into per-item chunks BEFORE extraction.
# Two reasons: (1) each item needs its own permalink for posting_url/dedupe,
# (2) a whole listing page overflows what a 7B model can reliably process —
# chunks keep every LLM call small.
@dataclass
class Chunk:
    text: str      # one item's text (e.g. one HN top-level comment)
    url: str       # that item's permalink — becomes posting_url / source_url

class Source(Protocol):
    """One platform's adapter. Every method is pure — no fetching in here;
    fetcher.py does the one and only HTTP call per URL (DESIGN.md §10). `kind`
    places it in JOB_SOURCES/QUESTION_SOURCES; `transport` and `delay_s`
    (phase 4 §11 steps 2 and 4) pick this source's transport and politeness
    delay, defaulting to the common case so most sources declare neither."""
    kind: Literal["jobs", "questions"]
    transport: Literal["httpx", "scrapling"]  # default "httpx" — see transport.py
    delay_s: float  # default config.REQUEST_DELAY_S; override for stricter/looser sites

    def seed_urls(self) -> list[str]: ...
    def next_links(self, page: Page) -> list[str]: ...
    def split_items(self, page: Page) -> list[Chunk]: ...

SOURCES: dict[str, Source] = {"hn": HNJobs(), "remoteok": RemoteOK(), ...}

def split_items(page: Page, source: str) -> list[Chunk]: ...  # dispatches via SOURCES

# transport.py — the transport a Source's own `transport` attribute selects;
# PageFetcher's robots.txt/retry/backoff policy stays identical either way
class Transport(Protocol):
    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse: ...

@dataclass
class TransportResponse:
    status: int
    body: bytes | str
    text: str  # cleaned page text where the transport can produce one, else ""

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
extract(chunk.text, schema):   # one chunk = one item's text, always small
  1. prompt local model with the chunk text + JSON schema of `schema`
  2. parse response as JSON, validate against `schema`
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

### Fetcher policy (fetcher.py) and transport (transport.py, phase 4 §11 step 2)

- Identify honestly: send the `USER_AGENT` constant (project name + contact) on
  every request this project makes, including fetching `robots.txt` itself —
  the WeWorkRemotely bug (§10 step 2) was exactly a request that didn't.
- Respect `robots.txt`: fetched with our own honest UA (not `RobotFileParser`'s
  internal default), cached per domain; a disallowed URL raises
  `FetchError("disallowed by robots.txt")` and is recorded like any other
  fetch failure.
- Retry once (`FETCH_RETRIES = 1`) with a short backoff on timeout or HTTP 5xx.
  HTTP 429 → back off `4 × REQUEST_DELAY_S` (or the source's own `delay_s`
  override) before the retry. Any other non-200, or a failed retry →
  `FetchError`. The pipeline records it and continues.
- **Transport is a `Source`-level choice, not a global one.** `PageFetcher`
  owns the policy above regardless of transport; it delegates the actual
  request to whichever `Transport` the run's source declares (default
  `"httpx"` — every source so far is a plain JSON/XML/text API and none
  read `Page.markdown`, so Scrapling's HTML-cleaning and stealth mode are
  currently unused weight). `"scrapling"` stays available and real, not
  removed, for a future source that genuinely needs stealth/JS-rendering.

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
      for chunk in sources.split_items(page, source):
          result = extractor.extract(chunk.text, schema)  # ExtractionFailed → record,
          repo.save_items(result.items, run,         #   continue with next chunk
                          url=chunk.url, tier=result.tier)  # dedupes internally
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
   multi-select as of phase 4 §11 step 3 — see below).
2. **Jobs** — searchable/filterable table: title, company, location, salary, source,
   scraped date. Row click opens a detail drawer with requirements list + posting /
   apply links.
3. **Questions** — same table pattern: question (truncated), company, role, round.
   Row click → drawer with full question text + source link.

No state library — server data via plain `fetch` + a small `useApi` hook.

**UI stack (amended for phase 2).** The MVP rule was "no component library —
Tailwind only". Phase 2 amends it: **shadcn/ui** primitives are allowed because
they are vendored source in `frontend/src/components/ui/` (reviewable code in the
repo, not a black-box dependency), plus **motion** (successor to framer-motion) for
animation, **sonner** for toasts, and **recharts** for dashboard charts. Rules:

- Vendored `components/ui/` files are generated starting points: type-checked and
  buildable, but exempt from the 300-line cap and slop review; edit them only for
  theme integration, keep app logic out of them.
- Animation is seasoning, not sauce: transitions on drawers/dialogs, count-up on
  stat cards, a pulse on the running badge — nothing animates without a reason.
- Everything else (views, hooks, api client) stays hand-written and reviewable.

**Phase 2 target look:** same light indigo/Inter identity plus a dark mode toggle,
skeleton loaders instead of dashes, toasts for run lifecycle events, proper empty
states with a CTA, a ⌘K command palette (switch views, search jobs), charts for
items-per-run and escalation trend, and a live progress panel for the active run.

**Frontend testing:** TypeScript strict mode is the safety net; no unit tests —
the UI is thin (fetch → render) and all logic lives behind the tested API. Any
change touching `frontend/` must pass `npm run build` (strict `tsc` + Vite build)
as part of the definition of done. Revisit if UI-side logic grows.

**Multi-select scrapes (phase 4 §11 step 3).** The backend keeps its existing
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
becomes a `sources/` package (§10), its tests mirror into `tests/sources/`.

## 8. Build order — one feature at a time, small commits

Workflow rule: each numbered step below is finished and validated (`pytest` + `mypy`
+ `ruff` green, plus the step-boundary smoke test) before the next step starts.
Within a step, commit each module + its tests as it lands (see CLAUDE.md "Git
workflow") — never mix two steps in one commit.

0. Project scaffolding: git init + `.gitignore` (done), Python 3.12 venv,
   `pyproject.toml` with pinned deps + ruff config, `README.md`, empty package layout.
1. `config.py`, `schemas.py`, `db/` + tests — the foundations everything depends on.
2. `llm/client.py`, `extractor.py` + tests — the cascade, proven against a fake LLM.
3. `fetcher.py`, `sources.py` (ONE job source), `pipeline.py` + tests.
4. `api/` + tests.
5. Frontend (dashboard → jobs → questions).
6. Second source type (interview questions) — by now it's just a new entry in
   `sources.py` and a schema, which is the test of whether the design held.

**Phase 1 (steps 0–6) is complete** — every step validated and smoke-tested.

## 9. Phase 2 build order — polish & usefulness

Same workflow rules as §8: one step at a time, small commits, all checks green
(now including `npm run build` for frontend changes), real smoke test at each
step boundary before moving on.

1. **Pre-extraction dedupe (backend).** The pipeline currently re-extracts every
   chunk and discards duplicates only at save time — a repeat HN run burns ~80
   minutes of LLM time to save nothing. Skip chunks whose normalized permalink is
   already stored (repo helper + pipeline check, counted as duplicates on the run)
   + tests. Smoke: re-run the HN jobs scrape; it must finish in seconds with
   `items_duplicate` > 0 and zero LLM calls for known chunks.
2. **Questions relevance gate (backend).** The local model saves junk ("exit
   interview questions for middle school"). Tighten the questions prompt: only
   concrete questions asked in a real tech interview, company must be named in
   the text, else return the empty list + tests pinning the prompt contract.
   Smoke: hn-interviews run; junk comments yield empty lists, not garbage rows.
3. **shadcn/ui foundation (frontend).** Vendor the primitives (button, dialog,
   sheet, table, select, badge, input, skeleton), add sonner, and swap the
   existing views to them at visual parity — no redesign in this step.
4. **Dashboard upgrade (frontend).** recharts (items saved per run, escalation
   trend), live progress panel for the active run (pages/saved/errors ticking),
   skeleton loaders, real empty states, toasts for run started/finished/failed.
5. **Delight pass (frontend).** motion transitions (drawer/dialog, stat count-up,
   running-badge pulse), ⌘K command palette (switch views, search jobs), dark
   mode toggle.
6. **Scheduled scrapes.** `schedules` table (kind, source, every_hours, enabled,
   last_run_at), a background thread in the app factory that starts due runs
   (skipped while another run is active), API endpoints + a small UI toggle on
   the dashboard + tests with a fake clock.
7. **Third source: RemoteOK** jobs via its public JSON API (`remoteok.com/api`,
   robots-friendly, attribution required — link back to the posting) — proves
   adding a source is still just seeds + chunking.
8. **Export & bookmarks.** CSV/JSON export endpoints for jobs/questions with the
   current filters applied + download buttons; a starred flag on jobs with a
   "starred only" filter.

**Phase 2 (steps 1–8) is complete** — every step validated and smoke-tested.
This step also triggered a size-driven refactor: `routes.py` and `repo.py` both
crossed the 300-line cap, so `routes.py`'s Pydantic models moved to `api/dto.py`
and `repo.py` became a `repo/` package (`_writes.py`, `_queries.py`,
`_schedules.py`, re-exported flat via `__init__.py` — no call site changed).

## 10. Phase 3 build order — plugin architecture + more platforms

Same workflow rules as §8/§9. Two things motivated this phase: `sources.py`'s
flat if/elif dispatch across three functions would hit the 300-line cap again
the moment a 4th or 5th platform landed (the exact failure mode phase 2 step 8
just hit for `routes.py`/`repo.py`) — so formalize the plugin shape *before*
adding more platforms, not after. Second, the interview-questions source is
still weak (HN comment search returns mostly meta-discussion, few real
questions); rather than scrape another forum, ingest curated, permissively-
licensed content instead.

**Sources investigated and rejected before writing this section** (so nobody
re-proposes them): **LeetCode Discuss** — `leetcode.com/robots.txt` disallows
`/graphql` and `/forums`; Discuss is a client-rendered SPA that fetches
everything through GraphQL, so even a stealth/browser fetch would pull data
through a channel they've explicitly closed to crawlers. **Blind** — returns an
anti-bot block page even for a plain `robots.txt` request. Both join Reddit
(§3, disallows all crawling) on the "do not revisit" list.

1. **Formalize the `Source` protocol + registry (backend, no behavior change).**
   Convert `scraper/sources.py` into a `scraper/sources/` package: a `Source`
   Protocol (`seed_urls`, `next_links`, `split_items` — no fetching, that stays
   in `fetcher.py`), one file per existing platform (`hn.py`, `remoteok.py`),
   and a `SOURCES` registry dict that the package's `__init__.py` dispatches
   through. `pipeline.py`'s calls (`sources.seed_urls(...)` etc.) do not change.
   Mirror the existing tests into `tests/sources/test_hn.py` etc. Smoke: full
   test suite passes unchanged (same proof pattern as the `repo/` package split)
   plus one real HN scrape to confirm the registry dispatch actually fetches.
2. **WeWorkRemotely job source.** Public RSS feed per category (e.g.
   `weworkremotely.com/categories/remote-programming-jobs.rss`) —
   `robots.txt` is `Allow: /` for `User-agent: *` with only account/admin paths
   disallowed. One `<item>` = one `Chunk`, `url` = the item's `<link>`.
3. **Arbeitnow job source.** Public JSON API (`arbeitnow.com/api/job-board-api`),
   `robots.txt` has no disallow rules at all. Structured fields (position,
   company, location, description) still routed through the same LLM
   extraction path as every other source, same reasoning as RemoteOK (§9 step 7).
4. **GitHub curated question-bank source.** Ingests
   `h5bp/Front-end-Developer-Interview-Questions` (MIT licensed, 60k+ stars) —
   flat markdown bullet lists of real questions, no answers, no company
   attribution — via `raw.githubusercontent.com`, which has no `robots.txt` at
   all (it's GitHub's CDN, built for programmatic access, same category as
   their REST API). One markdown file = one page; each top-level bullet
   (including its sub-bullets) = one `Chunk`. Requires:
   - `QuestionExtract.company` and `interview_questions.company` become
     nullable (§2) — this source is genuinely companyless, not a gap in the
     data. `question_hash` normalizes null company to `""` before hashing.
   - The questions relevance-gate prompt (§9 step 2) relaxes the "a specific
     company must be named" requirement to "a company is named, OR this is a
     well-known generic technical/behavioral question" — the company-naming
     rule was never really what filtered HN's junk (the rejected examples
     *did* name a company); the "concretely stated, actually asked" criteria
     did the real work, so relaxing this one clause doesn't reopen that hole.
   - Smoke: real fetch + local-model extraction of a few bullets from the live
     file, confirm `company: null` rows save correctly and dedupe against
     re-runs the same way company-attributed ones do.

**CLAUDE.md correction alongside step 1:** the original "Sources" section
listed LeetCode Discuss, Blind, and "relevant subreddits" as example
*low*-friction sources — every one of the three turned out to be high-friction
or fully disallowed once actually checked. Fixed to reflect what's been
verified, not what seemed plausible at the start.

## 11. Phase 4 build order — architecture for scale, not just more sources

Same workflow rules as §8/§9/§10. Phase 3 added three sources on top of the
plugin architecture from its own step 1; phase 4 is about the two axes that
get more valuable the more sources exist, done now while there are only 6
(cheap) rather than retrofitted at 15 (expensive) — plus one piece of UI
polish that doesn't depend on either.

1. **Split `sources/` by domain, not just by platform (backend, no behavior
   change).** Today `sources/` separates by *platform* (one file per site) but
   not by *domain* — `hn.py` even mixes `HNJobs` and `HNInterviews` in one
   file, and the registry is one flat dict distinguished only by reading each
   entry's `.kind`. Split into `sources/jobs/` and `sources/questions/`
   subpackages (§3), each with its own small registry; the top-level
   `sources/__init__.py` merges both into one `SOURCES` dict so
   `pipeline.py`'s calls (`sources.seed_urls(...)`, `sources.Chunk`, etc.)
   don't change at all — same re-export-flat pattern as the `repo/` package
   split (§9 step 8). `_base.py` (`Chunk`, `clean_html`, `MIN_CHUNK_CHARS`)
   stays shared at the top level; the one-line `_HN_PERMALINK` format string
   used by both HN sources is small enough to just duplicate rather than
   share (CLAUDE.md: "three lines is better than a premature abstraction").
   Smoke: full test suite passes unchanged, plus one real HN jobs scrape and
   one real HN interview-questions scrape to confirm both halves of the split
   still dispatch correctly.
2. **Extract a `Transport` protocol from `fetcher.py` (backend).** Confirmed
   before writing this: no source's `split_items` reads `Page.markdown` —
   every one of the 6 sources so far is a plain JSON/XML/plain-text API, so
   Scrapling's HTML-cleaning and stealth-fetch capability (the whole reason
   it was chosen originally, per CLAUDE.md's Stack section) sit completely
   unused. Define `Transport` (`get(url, *, timeout, headers) ->
   TransportResponse`) in `transport.py` (§3); `PageFetcher` keeps every bit
   of its policy (robots.txt, retry/backoff, honest UA) unchanged and just
   delegates the request to whichever transport it's given. Add
   `HttpxTransport` (promote the existing `httpx` dev dependency to a regular
   one — it's already pinned, just needs to stop being test-only) as the new
   default; keep `ScraplingTransport` as a real, still-tested alternative, not
   removed — available the moment a source genuinely needs stealth/JS
   rendering. Each `Source` declares `transport: Literal["httpx", "scrapling"]
   = "httpx"`; the code that builds a run's `PageFetcher` reads the source's
   choice. Existing `test_fetcher.py` fixtures move from monkeypatching
   `ScraplingFetcher.get` directly to faking the `Transport` protocol — less
   coupled to Scrapling's internals, more coupled to the actual contract.
   Smoke: one real scrape via `HttpxTransport` (any current source) and one
   real scrape forced onto `ScraplingTransport` (prove it still genuinely
   works, even though nothing defaults to it).
3. **Per-source politeness override, riding on step 2's metadata (backend).**
   `REQUEST_DELAY_S`/`FETCH_RETRIES` are global today; Arbeitnow's own API
   terms literally say "please do not abuse," while GitHub's CDN can take
   more load than a small job board. Add `delay_s: float =
   config.REQUEST_DELAY_S` to `Source` (§3) — most sources don't override it;
   the pipeline's `sleep(...)` call between pages reads the run's source's
   `delay_s` instead of the global constant directly. Smoke: not needed on
   its own (no new network path) — covered by step 2's smoke tests re-running
   with a source that sets a non-default `delay_s`.
4. **Multi-select sources in the "New scrape" modal (frontend only).** No
   backend change — the existing one-run-at-a-time invariant already fits
   this. `NewScrapeModal` becomes checkboxes; on submit, queue the selected
   sources and run them one at a time (start → poll `/api/runs/{id}` to a
   terminal status → start the next), matching the UI section's description
   above. `npm run build` gate as usual; no real backend smoke test needed
   since nothing server-side changes, but do one real manual multi-source run
   through the UI before calling this step done.
