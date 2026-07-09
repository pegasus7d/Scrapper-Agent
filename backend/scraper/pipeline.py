"""The scrape loop: fetch pages, split into chunks, extract, save.

Synchronous and boring on purpose (DESIGN.md §3). A run is executed in a
background thread by the API layer; its progress lives on the `runs` row.
Per-URL and per-chunk failures are recorded on the run and skipped; only an
unexpected crash fails the whole run — via the single broad `except Exception`
allowed in the codebase.
"""

import logging
import time
from collections.abc import Callable

from sqlalchemy.orm import Session

from backend import config
from backend.db import repo
from backend.db.models import Run
from backend.llm.client import FrontierClient, OllamaClient, ollama_available
from backend.schemas import JobExtract, QuestionExtract
from backend.scraper import sources
from backend.scraper.extractor import ExtractionFailed, Extractor
from backend.scraper.fetcher import FetchError, PageFetcher

logger = logging.getLogger(__name__)

ExtractSchema = JobExtract | QuestionExtract

_SCHEMAS: dict[str, type[ExtractSchema]] = {
    "jobs": JobExtract,
    "questions": QuestionExtract,
}


def build_extractor() -> Extractor[ExtractSchema]:
    """Wire the real two-tier cascade; without an API key the frontier stays dormant."""
    api_key = config.anthropic_api_key()
    if api_key is None:
        logger.warning("no ANTHROPIC_API_KEY set — escalation disabled, running local-only")
        return Extractor[ExtractSchema](OllamaClient(), frontier=None)
    return Extractor[ExtractSchema](OllamaClient(), frontier=FrontierClient(api_key))


def run_scrape(
    session: Session,
    kind: str,
    source: str,
    fetcher: PageFetcher,
    extractor: Extractor[ExtractSchema],
    sleep: Callable[[float], None] = time.sleep,
) -> Run:
    """Create a run and execute it to completion; returns the finished Run row."""
    if kind not in _SCHEMAS:
        raise ValueError(f"unknown kind: {kind}")
    run = repo.create_run(session, kind, source)
    return execute_run(session, run, fetcher, extractor, sleep)


def execute_run(
    session: Session,
    run: Run,
    fetcher: PageFetcher,
    extractor: Extractor[ExtractSchema],
    sleep: Callable[[float], None] = time.sleep,
) -> Run:
    """Execute an already-created run — the API creates the row first so it can
    return the run id, then executes in a background thread (DESIGN.md §3)."""
    try:
        if not ollama_available():
            repo.record_error(session, run, url="", error="ollama unreachable")
            repo.finish_run(session, run, "failed")
            return run
        schema = _SCHEMAS[run.kind]
        status = _scrape_loop(session, run, run.source, schema, fetcher, extractor, sleep)
        run.escalations = extractor.escalations_used
        repo.finish_run(session, run, status)
    except Exception as error:  # the single allowed broad catch (DESIGN.md §3)
        logger.exception("run %s crashed", run.id)
        repo.record_error(session, run, url="", error=str(error))
        repo.finish_run(session, run, "failed")
    return run


def _scrape_loop(
    session: Session,
    run: Run,
    source: str,
    schema: type[ExtractSchema],
    fetcher: PageFetcher,
    extractor: Extractor[ExtractSchema],
    sleep: Callable[[float], None],
) -> str:
    """Walk the source's pages breadth-first; returns the terminal run status."""
    queue = sources.seed_urls(source)
    seen: set[str] = set()
    while queue and run.pages_fetched < config.MAX_PAGES_PER_RUN:
        if repo.cancel_requested(session, run):
            return "cancelled"
        url = repo.normalize_url(queue.pop(0))
        if url in seen:
            continue
        seen.add(url)
        try:
            page = fetcher.fetch(url)
        except FetchError as error:
            repo.record_error(session, run, url, str(error))
            continue
        run.pages_fetched += 1
        session.commit()
        try:
            chunks = sources.split_items(page, source)
            links = sources.next_links(page, source)
        except ValueError as error:  # malformed payload — sources contract
            repo.record_error(session, run, url, str(error))
            continue
        if not _extract_chunks(session, run, source, schema, extractor, chunks):
            return "cancelled"
        queue.extend(links)
        sleep(config.REQUEST_DELAY_S)
    return "completed"


def _extract_chunks(
    session: Session,
    run: Run,
    source: str,
    schema: type[ExtractSchema],
    extractor: Extractor[ExtractSchema],
    chunks: list[sources.Chunk],
) -> bool:
    """Extract and save chunks; a failed chunk is recorded, not fatal.

    One page can carry hundreds of chunks at ~20s of LLM time each, so cancel
    is re-checked between chunks — returns False when the run was cancelled.
    """
    for chunk in chunks:
        if repo.cancel_requested(session, run):
            return False
        if repo.item_url_exists(session, run.kind, chunk.url):
            # Already stored on a previous run — don't spend LLM time on it.
            run.items_duplicate += 1
            session.commit()
            continue
        try:
            result = extractor.extract(chunk.text, schema)
        except ExtractionFailed as error:
            repo.record_error(session, run, chunk.url, str(error))
            continue
        for item in result.items:
            _save_item(session, run, source, result.tier, chunk.url, item)
    return True


def _save_item(
    session: Session, run: Run, source: str, tier: str, url: str, item: ExtractSchema
) -> bool:
    """Route one extracted item to the matching repo saver."""
    if isinstance(item, JobExtract):
        return repo.save_job(session, item, posting_url=url, source=source, tier=tier, run=run)
    return repo.save_question(session, item, source_url=url, source=source, tier=tier, run=run)
