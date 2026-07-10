# Hirable

An AI agent for job discovery and application support — scrapes **job postings**,
**interview questions**, and now company career pages, extracts them into
structured data with a two-tier LLM cascade, and serves them through a small web UI.
(Formerly "Scraper Agent" — renamed in phase 8 as the project grew past scraping
into resume-matched search, company intelligence, and application pipeline
tracking.)

**How it works, in one paragraph:** a Python pipeline fetches pages through a
`Transport` protocol — plain `httpx` by default, with
[Scrapling](https://github.com/D4Vinci/Scrapling) available per-source for anything
that genuinely needs stealth/JS rendering — hands the cleaned text to a local LLM
(via Ollama) that extracts structured fields, validates the output against strict
Pydantic schemas, and only escalates the rare failed pages to a paid frontier model
(Claude Haiku) — so scraping thousands of pages costs approximately nothing. Runs
are scheduled and queued through Huey (`SqliteHuey`, no separate services). Results
land in SQLite, deduplicated, and a FastAPI backend + React UI let you browse jobs,
questions, and live scrape-run status.

- Product idea and rationale: [[docs/IDEA.md]]
- Technical contract (DB models, modules, API, test plan): [[docs/DESIGN.md]]
- Module contracts, extraction cascade, fetcher/pipeline internals: [[docs/ARCHITECTURE.md]]
- Contributor rules (code quality, testing, git workflow): [[CLAUDE.md]]
- How this project actually moves from idea to shipped phase: [[docs/WORKFLOW.md]]

> **Status:** phases 1–6 complete (see [[docs/WORKFLOW.md]] and [[docs/PHASE6.md]]).
> **9 sources** across jobs and questions — jobs: HN "Who is hiring?",
> RemoteOK, WeWorkRemotely, Arbeitnow, Himalayas, RemoteJobs.org; questions:
> HN comment search, GitHub's h5bp interview-questions bank, FAQGURU
> (Reddit's robots.txt disallows crawling, so it's excluded — see [[docs/DESIGN.md]]
> §3, and `backend/scraper/sources/`'s own CLAUDE.md for the full
> verify-before-adding history). Hybrid search (⌘K — `sqlite-vec` similarity +
> FTS5 keyword, reciprocal rank fusion) and live run updates (SSE) are real,
> not just planned. Scheduling and multi-source queueing run
> through [[docs/PHASE5.md|Huey]] (`SqliteHuey`, no Redis) — manual runs, a
> once-a-minute periodic dispatch for user-defined schedules, and multi-select
> batch runs all go through the same task pipeline.

## Prerequisites

- **Python 3.12+** and **uv** (used for all env/package management):
  ```sh
  brew install python@3.12 uv
  ```
- **Ollama** running locally, with the extraction and embedding models pulled:
  ```sh
  brew install ollama
  ollama pull qwen2.5:7b-instruct
  ollama pull nomic-embed-text   # powers search (real 768-dim output, PHASE6.md step 7)
  ```
- **Node.js 20+** (for the frontend): `brew install node`
- *(Optional)* An Anthropic API key for the escalation tier. Without it the scraper
  still works — hard pages are recorded as failures instead of escalating.

## Setup

```sh
git clone <repo-url> && cd hirable

# Create and activate a virtual environment (Python 3.12, via uv)
uv venv --python 3.12 .venv
source .venv/bin/activate

# Install the backend with dev dependencies (always uv pip, never plain pip)
uv pip install -e ".[dev]"

# Secrets (optional, for the escalation tier)
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env   # .env is gitignored
```

## Running

One command starts everything (backend on 8000, frontend on 5173; Ctrl-C stops both):

```sh
./run.sh
```

Open http://localhost:5173, click **New scrape**, pick a kind (`jobs` /
`questions`) and one or more sources (multi-select queues them and runs them
one at a time server-side via Huey), and watch the run progress on the
dashboard. Schedules (recurring runs on a fixed interval) are managed from
the same UI and dispatched by a Huey periodic task that ticks once a minute.

<details>
<summary>Manual commands (what run.sh does)</summary>

**Backend** (from the repo root, venv active):

```sh
uvicorn --factory backend.api.main:create_app --port 8000
```

**Frontend** (separate terminal):

```sh
cd frontend
npm install
npm run dev        # serves the UI at http://localhost:5173
```

</details>

## Checks

Run before every commit (this is the definition of done):

```sh
pytest                 # all unit tests — no network, no LLM calls
mypy backend           # type checking
ruff check .           # lint
ruff format --check .  # formatting
```
