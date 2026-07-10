"""Project-wide constants, secrets loading, and logging setup.

Every tunable lives here — no magic values elsewhere (CLAUDE.md). Secrets come
from the environment (a gitignored .env is loaded at import); the Anthropic key
is optional by design — without it the app runs free/local-only.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

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
USER_AGENT = "hirable/0.1 (personal research tool; debayanbiswas1111@gmail.com)"
API_PORT = 8000
CORS_ORIGINS = ["http://localhost:5173"]
DATABASE_URL = "sqlite:///hirable.db"
# robots.txt confirmed (PHASE7.md step 5): only /companies?* (query-string
# filtered views) is disallowed — the bare listing page below is not.
YC_COMPANIES_URL = "https://www.ycombinator.com/companies"
# Wikipedia's own revenue-ranked table (PHASE8.md step 6) — the closest
# real, public, scrape-friendly proxy for "Fortune 500," which paywalls its
# own full list. en.wikipedia.org/robots.txt only disallows /w/ action
# paths, not /wiki/ article pages.
LARGEST_US_COMPANIES_URL = (
    "https://en.wikipedia.org/wiki/List_of_largest_companies_in_the_United_States_by_revenue"
)
# a16z portfolio (PHASE8.md step 9) — no robots.txt at all (404), treated as
# no restrictions (same interpretation fetcher.py's _fetch_robots_lines
# already codifies). The full 849-company portfolio ships inline in a
# `window.a16z_portfolio_companies` JS array on this one page — confirmed
# real, no pagination/scroll/JS-rendering needed unlike YC.
A16Z_PORTFOLIO_URL = "https://a16z.com/portfolio/"
# Persistent logs (PHASE8.md step 8) — real gap once scheduled company
# automation (step 7) runs unattended: stderr alone leaves no record when
# nobody's watching a terminal. A home-lab, single-user tool, not a
# service under real log-volume pressure — 5 MB/file x 3 backups (~20 MB
# total) is a real bound, not unbounded growth, without needing to tune it.
LOG_FILE = "hirable.log"
LOG_MAX_BYTES = 5 * 1024 * 1024
LOG_BACKUP_COUNT = 3

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def anthropic_api_key() -> str | None:
    """Return the Anthropic API key, or None when running free/local-only."""
    return os.environ.get("ANTHROPIC_API_KEY")


def configure_logging() -> None:
    """Configure stderr + a rotating log file for the whole app; safe to
    call more than once — logging.basicConfig() is itself a no-op once the
    root logger already has handlers, and the same check below guards the
    file handler this function adds on top of it."""
    root = logging.getLogger()
    if root.handlers:
        return
    logging.basicConfig(format=_LOG_FORMAT, level=logging.INFO)
    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
    )
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(file_handler)
