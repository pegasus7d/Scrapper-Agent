"""Run lifecycle, dedupe normalization, and item saving (DESIGN.md §2)."""

import hashlib
import logging
import re
from collections.abc import Callable
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session

from backend import config
from backend.db import fts, migrate, vectors
from backend.db.models import InterviewQuestion, Job, Run
from backend.schemas import JobExtract, QuestionExtract

logger = logging.getLogger(__name__)

MAX_RUN_ERRORS = 100
_TRACKING_PARAMS = {"ref", "gclid", "fbclid"}
_TRACKING_PREFIXES = ("utm_",)
_WHITESPACE = re.compile(r"\s+")


def make_engine(database_url: str = config.DATABASE_URL) -> Engine:
    """Create an engine, load sqlite-vec, and bring the schema to head via
    Alembic (PHASE7.md step 1) — replaces the old create_all() +
    ad-hoc-ALTER-TABLE pattern (phase 6 step 3), which had no single record
    of which migrations had actually been applied to a given database.

    Extension registration (vectors.register_vec_extension) must happen
    before any migration runs: a migration may CREATE VIRTUAL TABLE ...
    USING vec0, and that module only exists once the extension is loaded on
    the connection.
    """
    engine = create_engine(database_url)
    vectors.register_vec_extension(engine)
    migrate.run_migrations(engine, database_url)
    return engine


def normalize_url(url: str) -> str:
    """Strip tracking query params so one item has one URL.

    Deliberately keeps the fragment: it used to be stripped on the theory that
    fragments are never part of a resource's identity, but no source has ever
    needed that, and the GitHub question-bank source (PHASE3.md step 4)
    genuinely does — its `#L{line}` anchor is the only thing that makes each
    question's URL distinct from its neighbors in the same file. Without it,
    every question after the first collapses onto one URL and item_url_exists
    silently treats the rest as already-known duplicates forever.
    """
    parts = urlparse(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _TRACKING_PARAMS and not key.startswith(_TRACKING_PREFIXES)
    ]
    return urlunparse(parts._replace(query=urlencode(kept)))


def question_hash(company: str | None, question: str) -> str:
    """Content hash used to dedupe questions across formatting differences.

    A null company (PHASE3.md step 4) normalizes to "" so it still hashes
    deterministically instead of raising.
    """
    normalized = _WHITESPACE.sub(" ", f"{company or ''} {question}".lower()).strip()
    return hashlib.sha256(normalized.encode()).hexdigest()


def create_run(session: Session, kind: str, source: str, model: str = config.LOCAL_MODEL) -> Run:
    """Insert and return a new run in "running" state."""
    run = Run(kind=kind, source=source, model=model, status="running", started_at=datetime.now(UTC))
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
    embed: Callable[[str], bytes] | None = None,
) -> bool:
    """Save one job; returns False (counting a duplicate) if already stored.

    Always indexed into job_search_fts for keyword search (PHASE6.md step
    8) — pure local SQLite, no reason to gate it. `embed`, when given,
    additionally computes the job's embedding and inserts it into the
    job_embeddings vec0 table, same transaction (PHASE6.md step 7) — None
    everywhere except the real run path, so no test needs a real Ollama call.
    """
    url = normalize_url(posting_url)
    exists = session.scalar(select(Job.id).where(Job.posting_url == url))
    if exists is not None:
        run.items_duplicate += 1
        session.commit()
        logger.debug("duplicate job skipped: %s", url)
        return False
    job = Job(
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
    session.add(job)
    run.items_saved += 1
    session.flush()  # need job.id before the fts5/vec0 inserts
    fts.index_job(
        session,
        job.id,
        title=extract.title,
        company=extract.company,
        location=extract.location,
        salary=extract.salary,
        requirements=extract.requirements,
    )
    if embed is not None:
        text_for_embedding = f"{extract.title} at {extract.company}. " + " ".join(
            extract.requirements
        )
        vectors.save_job_embedding(session, job.id, embed(text_for_embedding))
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
    embed: Callable[[str], bytes] | None = None,
) -> bool:
    """Save one question; returns False (counting a duplicate) if already stored.

    Always indexed into question_search_fts; `embed`: see save_job's
    docstring — same same-transaction contract.
    """
    content_hash = question_hash(extract.company, extract.question)
    exists = session.scalar(
        select(InterviewQuestion.id).where(InterviewQuestion.question_hash == content_hash)
    )
    if exists is not None:
        run.items_duplicate += 1
        session.commit()
        logger.debug("duplicate question skipped: %s", content_hash)
        return False
    question = InterviewQuestion(
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
    session.add(question)
    run.items_saved += 1
    session.flush()  # need question.id before the fts5/vec0 inserts
    fts.index_question(
        session, question.id, question=extract.question, company=extract.company, role=extract.role
    )
    if embed is not None:
        vectors.save_question_embedding(session, question.id, embed(extract.question))
    session.commit()
    return True


def item_url_exists(session: Session, kind: str, url: str) -> bool:
    """True when this permalink already has stored items — lets the pipeline skip
    the chunk before spending LLM time on it (PHASE2.md step 1)."""
    normalized = normalize_url(url)
    if kind == "jobs":
        return session.scalar(select(Job.id).where(Job.posting_url == normalized)) is not None
    query = select(InterviewQuestion.id).where(InterviewQuestion.source_url == normalized)
    return session.scalar(query.limit(1)) is not None
