# Architecture — module contracts and core algorithms

Read [[docs/DESIGN.md]] first — this file is the deep-dive companion to its §3
(Module layout): the actual code-level contracts and algorithms behind the
module tree, split out because they made §3 the largest single chunk of
DESIGN.md (227 of 514 lines) and most `/loop` iterations don't need this
level of detail just to orient themselves. Split the same way the
`PHASE{N}.md` files were split out of DESIGN.md's old build-order
section — move the content that's dense and situational, keep the content
that's needed for general orientation.

Every existing `(DESIGN.md §3)` citation in code comments and other docs
stays valid: §3 still exists, still covers this material conceptually, and
now points here for the actual detail instead of containing it inline.

## Key contracts

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
    fetcher.py does the one and only HTTP call per URL (PHASE3.md). `kind`
    places it in JOB_SOURCES/QUESTION_SOURCES; `transport` and `delay_s`
    (PHASE4.md steps 2 and 3) pick this source's transport and politeness
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

## Cascade algorithm (extractor.py)

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

## Fetcher policy (fetcher.py) and transport (transport.py, PHASE4.md step 2)

- Identify honestly: send the `USER_AGENT` constant (project name + contact) on
  every request this project makes, including fetching `robots.txt` itself —
  the WeWorkRemotely bug (PHASE3.md step 2) was exactly a request that didn't.
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

## Pipeline loop (pipeline.py)

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

The loop is synchronous and boring on purpose. A run is enqueued onto Huey
(`tasks.py`, [[docs/phases/PHASE5.md]]) and executed on the consumer thread; its progress
is readable from the `runs` row at any time — that is the entire "job
status" mechanism, no separate queue-monitoring infra to build.

The whole of `run_scrape`/`execute_run` is wrapped in one `try/except
Exception` (the single allowed broad catch in the codebase): an unexpected
crash marks the run `"failed"` with the error message instead of leaving a
zombie `"running"` row.
