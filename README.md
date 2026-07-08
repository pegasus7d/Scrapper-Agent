# Scraper Agent

An AI agent that scrapes **job postings** and **interview questions** from public
sources, extracts them into structured data with a two-tier LLM cascade, and serves
them through a small web UI.

**How it works, in one paragraph:** a Python pipeline fetches pages with
[Scrapling](https://github.com/D4Vinci/Scrapling), hands the cleaned text to a local
LLM (via Ollama) that extracts structured fields, validates the output against strict
Pydantic schemas, and only escalates the rare failed pages to a paid frontier model
(Claude Haiku) — so scraping thousands of pages costs approximately nothing. Results
land in SQLite, deduplicated, and a FastAPI backend + React UI let you browse jobs,
questions, and live scrape-run status.

- Product idea and rationale: [`IDEA.md`](IDEA.md)
- Technical contract (DB models, modules, API, test plan): [`DESIGN.md`](DESIGN.md)
- Contributor rules (code quality, testing, git workflow): [`CLAUDE.md`](CLAUDE.md)

> **Status:** design phase complete; backend/frontend are being built step by step
> (see build order in `DESIGN.md` §8). Sections below describe how running the app
> will work; commands are updated as each piece lands.

## Prerequisites

- **Python 3.12+** — macOS system Python (3.9) is too old:
  ```sh
  brew install python@3.12
  ```
- **Ollama** running locally, with the extraction model pulled:
  ```sh
  brew install ollama
  ollama pull qwen2.5:7b-instruct
  ```
- **Node.js 20+** (for the frontend): `brew install node`
- *(Optional)* An Anthropic API key for the escalation tier. Without it the scraper
  still works — hard pages are recorded as failures instead of escalating.

## Setup

```sh
git clone <repo-url> && cd scraper-agent

# Create and activate a virtual environment (Python 3.12)
python3.12 -m venv .venv
source .venv/bin/activate

# Install the backend with dev dependencies
pip install -e ".[dev]"

# Secrets (optional, for the escalation tier)
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env   # .env is gitignored
```

## Running

**Backend** (from the repo root, venv active):

```sh
uvicorn backend.api.main:app --reload --port 8000
```

**Frontend** (separate terminal):

```sh
cd frontend
npm install
npm run dev        # serves the UI at http://localhost:5173
```

Open http://localhost:5173, click **New scrape**, pick a kind (`jobs` /
`questions`) and a source, and watch the run progress on the dashboard.

## Checks

Run before every commit (this is the definition of done):

```sh
pytest                 # all unit tests — no network, no LLM calls
mypy backend           # type checking
ruff check .           # lint
ruff format --check .  # formatting
```
