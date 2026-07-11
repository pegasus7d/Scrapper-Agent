"""Single-URL job intake (PHASE13.md step 11) — every existing `Source`
enumerates many items from one board page (`seed_urls`/`split_items`); a
link shared over chat is one arbitrary URL from anywhere, a genuinely
different shape. Reuses the existing fetch/extract/save primitives
directly instead of forcing this through the `Source` protocol's chunk
loop.

`PageFetcher` enforces `robots.txt` per-domain automatically here exactly
as it does for every scheduled scrape — a shared LinkedIn link is
correctly blocked the same way a scheduled LinkedIn scrape would be, no
new per-domain ToS review needed for this feature specifically.
"""

import logging
import re

from sqlalchemy.orm import Session

from backend.db import repo
from backend.schemas import JobExtract
from backend.scraper.extractor import ExtractionFailed, Extractor
from backend.scraper.fetcher import FetchError, PageFetcher
from backend.scraper.pipeline import ExtractSchema
from backend.scraper.sources._base import clean_html

logger = logging.getLogger(__name__)

INTAKE_SOURCE = "whatsapp"

_URL_PATTERN = re.compile(r"https?://\S+")


def extract_urls(text: str) -> list[str]:
    """Real URLs in a message's text — a plain regex, not an LLM call,
    cheap and exact for this."""
    return _URL_PATTERN.findall(text)


def intake_job_link(
    session: Session, url: str, fetcher: PageFetcher, extractor: Extractor[ExtractSchema]
) -> bool:
    """Fetch one shared link and try to save it as a job. Real Job.run_id
    needs a real Run row to attach to (every other job already has one);
    one is created here so a WhatsApp-sourced job shows up in the
    Dashboard/Runs view the same way any scheduled scrape's jobs do, not
    as a second, unobserved save path. Returns True on a real, new save."""
    run = repo.create_run(session, kind="jobs", source=INTAKE_SOURCE)
    try:
        page = fetcher.fetch(url)
    except FetchError as error:
        logger.warning("whatsapp intake: fetch failed for %s: %s", url, error)
        repo.record_error(session, run, url, str(error))
        repo.finish_run(session, run, "failed")
        return False

    text = clean_html(page.raw)
    try:
        result = extractor.extract(text, JobExtract)
    except ExtractionFailed as error:
        logger.warning("whatsapp intake: extraction failed for %s: %s", url, error)
        repo.record_error(session, run, url, str(error))
        repo.finish_run(session, run, "failed")
        return False

    saved = False
    for item in result.items:
        # Always a JobExtract at runtime (JobExtract is the only schema
        # ever passed to extract() above); the isinstance narrows the
        # static ExtractSchema union type the same way pipeline.py's own
        # _save_item already does for the exact same reason.
        if isinstance(item, JobExtract) and repo.save_job(
            session, item, posting_url=url, source=INTAKE_SOURCE, tier=result.tier, run=run
        ):
            saved = True
    repo.finish_run(session, run, "completed")
    return saved
