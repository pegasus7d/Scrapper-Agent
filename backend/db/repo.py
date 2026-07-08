"""Write-side persistence: run lifecycle, dedupe normalization, item saving.

All dedupe decisions live here (DESIGN.md §2). Read-side queries for the API
are added with the API layer.
"""

import hashlib
import logging
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from backend import config
from backend.db.models import Base, InterviewQuestion, Job, Run
from backend.schemas import JobExtract, QuestionExtract

logger = logging.getLogger(__name__)

MAX_RUN_ERRORS = 100
_TRACKING_PARAMS = {"ref", "gclid", "fbclid"}
_TRACKING_PREFIXES = ("utm_",)
_WHITESPACE = re.compile(r"\s+")


def make_engine(database_url: str = config.DATABASE_URL) -> Engine:
    """Create an engine and ensure all tables exist."""
    engine = create_engine(database_url)
    Base.metadata.create_all(engine)
    return engine


def normalize_url(url: str) -> str:
    """Strip the fragment and tracking query params so one item has one URL."""
    parts = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _TRACKING_PARAMS and not key.startswith(_TRACKING_PREFIXES)
    ]
    return urlunparse(parts._replace(query=urlencode(kept), fragment=""))


def question_hash(company: str, question: str) -> str:
    """Content hash used to dedupe questions across formatting differences."""
    normalized = _WHITESPACE.sub(" ", f"{company} {question}".lower()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def create_run(session: Session, kind: str, source: str) -> Run:
    """Insert and return a new run in "running" state."""
    run = Run(kind=kind, source=source, status="running", started_at=datetime.now(UTC))
    session.add(run)
    session.commit()
    return run


def finish_run(session: Session, run: Run, status: str = "completed") -> None:
    """Mark the run finished with the given terminal status."""
    run.status = status
    run.finished_at = datetime.now(UTC)
    session.commit()
    logger.info("run %s finished: %s (%s items)", run.id, status, run.items_saved)


def record_error(session: Session, run: Run, url: str, error: str) -> None:
    """Append one error to the run, keeping at most MAX_RUN_ERRORS entries."""
    if len(run.errors) < MAX_RUN_ERRORS:
        # JSON columns don't track in-place mutation — reassign instead.
        run.errors = [*run.errors, {"url": url, "error": error}]
    session.commit()
    logger.warning("run %s error at %s: %s", run.id, url, error)


def request_cancel(session: Session, run_id: int) -> bool:
    """Set the cancel flag on a run; returns False when the run doesn't exist."""
    run = session.get(Run, run_id)
    if run is None or run.status != "running":
        return False
    run.cancel_requested = True
    session.commit()
    return True


def cancel_requested(session: Session, run: Run) -> bool:
    """Re-read the cancel flag from the DB (it is set by the API thread)."""
    session.refresh(run)
    return run.cancel_requested


def active_run_exists(session: Session) -> bool:
    """True when any run is still in "running" state."""
    return session.scalar(select(Run.id).where(Run.status == "running")) is not None


def recover_stale_runs(session: Session) -> int:
    """Mark leftover "running" rows as failed after a restart; returns the count."""
    stale = session.scalars(select(Run).where(Run.status == "running")).all()
    for run in stale:
        run.status = "failed"
        run.errors = [*run.errors, {"url": "", "error": "interrupted by restart"}]
        run.finished_at = datetime.now(UTC)
    session.commit()
    if stale:
        logger.warning("recovered %d stale run(s) left in running state", len(stale))
    return len(stale)


def save_job(
    session: Session,
    extract: JobExtract,
    *,
    posting_url: str,
    source: str,
    tier: str,
    run: Run,
) -> bool:
    """Save one job; returns False (counting a duplicate) if already stored."""
    url = normalize_url(posting_url)
    exists = session.scalar(select(Job.id).where(Job.posting_url == url))
    if exists is not None:
        run.items_duplicate += 1
        session.commit()
        logger.debug("duplicate job skipped: %s", url)
        return False
    session.add(
        Job(
            title=extract.title,
            company=extract.company,
            location=extract.location,
            salary=extract.salary,
            requirements=extract.requirements,
            posting_url=url,
            apply_url=extract.apply_url,
            source=source,
            extraction_tier=tier,
            scraped_at=datetime.now(UTC),
            run_id=run.id,
        )
    )
    run.items_saved += 1
    session.commit()
    return True


def save_question(
    session: Session,
    extract: QuestionExtract,
    *,
    source_url: str,
    source: str,
    tier: str,
    run: Run,
) -> bool:
    """Save one question; returns False (counting a duplicate) if already stored."""
    content_hash = question_hash(extract.company, extract.question)
    exists = session.scalar(
        select(InterviewQuestion.id).where(InterviewQuestion.question_hash == content_hash)
    )
    if exists is not None:
        run.items_duplicate += 1
        session.commit()
        logger.debug("duplicate question skipped: %s", content_hash)
        return False
    session.add(
        InterviewQuestion(
            company=extract.company,
            role=extract.role,
            question=extract.question,
            round=extract.round,
            source_url=normalize_url(source_url),
            question_hash=content_hash,
            source=source,
            extraction_tier=tier,
            scraped_at=datetime.now(UTC),
            run_id=run.id,
        )
    )
    run.items_saved += 1
    session.commit()
    return True
