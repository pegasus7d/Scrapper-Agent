"""Persistence layer: run lifecycle, dedupe normalization, saving, queries.

All dedupe decisions live here (DESIGN.md §2). The read-side queries at the
bottom serve the API's list endpoints ({items, total} pagination) and stats.
"""

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import CompoundSelect, Engine, Select, create_engine, func, select
from sqlalchemy.orm import Session

from backend import config
from backend.db.models import Base, InterviewQuestion, Job, Run, Schedule
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


def item_url_exists(session: Session, kind: str, url: str) -> bool:
    """True when this permalink already has stored items — lets the pipeline skip
    the chunk before spending LLM time on it (DESIGN.md §9 step 1)."""
    normalized = normalize_url(url)
    if kind == "jobs":
        return session.scalar(select(Job.id).where(Job.posting_url == normalized)) is not None
    query = select(InterviewQuestion.id).where(InterviewQuestion.source_url == normalized)
    return session.scalar(query.limit(1)) is not None


@dataclass
class Stats:
    """Dashboard totals (DESIGN.md §4)."""

    jobs: int
    questions: int
    companies: int
    escalation_rate: float  # fraction of saved items that needed the frontier tier


def get_run(session: Session, run_id: int) -> Run | None:
    return session.get(Run, run_id)


def list_runs(session: Session, *, limit: int, offset: int) -> tuple[list[Run], int]:
    """Return one page of runs, newest first, plus the total count."""
    return _paginate(session, select(Run).order_by(Run.id.desc()), limit, offset)


def list_jobs(
    session: Session,
    *,
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Job], int]:
    """Return one page of jobs (newest first) matching the filters, plus the total."""
    query = select(Job).order_by(Job.id.desc())
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))
    if source:
        query = query.where(Job.source == source)
    if q:
        query = query.where(Job.title.ilike(f"%{q}%"))
    return _paginate(session, query, limit, offset)


def list_questions(
    session: Session,
    *,
    company: str | None = None,
    round_: str | None = None,
    q: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[InterviewQuestion], int]:
    """Return one page of questions (newest first) matching the filters, plus the total."""
    query = select(InterviewQuestion).order_by(InterviewQuestion.id.desc())
    if company:
        query = query.where(InterviewQuestion.company.ilike(f"%{company}%"))
    if round_:
        query = query.where(InterviewQuestion.round == round_)
    if q:
        query = query.where(InterviewQuestion.question.ilike(f"%{q}%"))
    return _paginate(session, query, limit, offset)


def compute_stats(session: Session) -> Stats:
    """Compute the dashboard totals in one place, so routes stay logic-free."""
    jobs = _count(session, select(Job))
    questions = _count(session, select(InterviewQuestion))
    companies_union = select(Job.company).union(select(InterviewQuestion.company))
    companies = _count(session, companies_union)
    frontier = _count(session, select(Job).where(Job.extraction_tier == "frontier")) + _count(
        session, select(InterviewQuestion).where(InterviewQuestion.extraction_tier == "frontier")
    )
    total = jobs + questions
    rate = frontier / total if total else 0.0
    return Stats(jobs=jobs, questions=questions, companies=companies, escalation_rate=rate)


def create_schedule(session: Session, kind: str, source: str, every_hours: int) -> Schedule:
    """Insert and return a new enabled schedule."""
    schedule = Schedule(kind=kind, source=source, every_hours=every_hours)
    session.add(schedule)
    session.commit()
    return schedule


def list_schedules(session: Session) -> list[Schedule]:
    """Return every schedule, oldest first."""
    return list(session.scalars(select(Schedule).order_by(Schedule.id)).all())


def set_schedule_enabled(session: Session, schedule_id: int, enabled: bool) -> Schedule | None:
    """Flip a schedule's enabled flag; returns None when it doesn't exist."""
    schedule = session.get(Schedule, schedule_id)
    if schedule is None:
        return None
    schedule.enabled = enabled
    session.commit()
    return schedule


def due_schedules(session: Session, now: datetime) -> list[Schedule]:
    """Enabled schedules that have never run, or whose interval has elapsed."""
    # SQLite round-trips DateTime columns as naive (same convention as
    # started_at/finished_at elsewhere) — drop tzinfo from `now` to compare.
    naive_now = now.replace(tzinfo=None)
    enabled = session.scalars(select(Schedule).where(Schedule.enabled)).all()
    return [
        schedule
        for schedule in enabled
        if schedule.last_run_at is None
        or naive_now - schedule.last_run_at >= timedelta(hours=schedule.every_hours)
    ]


def mark_schedule_run(session: Session, schedule: Schedule, now: datetime) -> None:
    """Record that a schedule just triggered a run, resetting its interval clock."""
    schedule.last_run_at = now
    session.commit()


def _paginate[T](
    session: Session, query: Select[tuple[T]], limit: int, offset: int
) -> tuple[list[T], int]:
    total = _count(session, query)
    rows = session.scalars(query.limit(limit).offset(offset)).all()
    return list(rows), total


def _count[T](session: Session, query: Select[tuple[T]] | CompoundSelect[tuple[T]]) -> int:
    return session.scalar(select(func.count()).select_from(query.subquery())) or 0
