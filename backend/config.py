"""Project-wide constants, secrets loading, and logging setup.

Every tunable lives here — no magic values elsewhere (CLAUDE.md). Secrets come
from the environment (a gitignored .env is loaded at import); the Anthropic key
is optional by design — without it the app runs free/local-only.
"""

import logging
import os

from dotenv import load_dotenv

load_dotenv()

LOCAL_MODEL = "qwen2.5:7b-instruct"
FRONTIER_MODEL = "claude-haiku-4-5-20251001"
# nomic-embed-text: real 768-dim output confirmed via ollama.embed() (PHASE6.md
# step 7) — needs its own `ollama pull nomic-embed-text`, documented in README.
EMBED_MODEL = "nomic-embed-text"
EMBED_DIM = 768
MAX_ESCALATIONS_PER_RUN = 25
FRONTIER_MAX_TOKENS = 2048
FETCH_TIMEOUT_S = 20
FETCH_RETRIES = 1
MAX_PAGES_PER_RUN = 30
REQUEST_DELAY_S = 2.0
USER_AGENT = "scraper-agent/0.1 (personal research tool; debayanbiswas1111@gmail.com)"
API_PORT = 8000
CORS_ORIGINS = ["http://localhost:5173"]
DATABASE_URL = "sqlite:///scraper.db"
# robots.txt confirmed (PHASE7.md step 5): only /companies?* (query-string
# filtered views) is disallowed — the bare listing page below is not.
YC_COMPANIES_URL = "https://www.ycombinator.com/companies"

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def anthropic_api_key() -> str | None:
    """Return the Anthropic API key, or None when running free/local-only."""
    return os.environ.get("ANTHROPIC_API_KEY")


def configure_logging() -> None:
    """Configure stderr logging for the whole app; safe to call more than once."""
    logging.basicConfig(format=_LOG_FORMAT, level=logging.INFO)
