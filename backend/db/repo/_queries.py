"""Read-side queries: paginated lists, filters, export, dashboard stats.

Serves the API's list endpoints ({items, total} pagination) and the
unpaginated export endpoints (DESIGN.md §4, PHASE2.md step 8).
"""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import CompoundSelect, Select, func, select
from sqlalchemy.orm import Session

from backend.db.models import Company, InterviewQuestion, Job, Run


@dataclass
class Stats:
    """Dashboard totals (DESIGN.md §4)."""

    jobs: int
    questions: int
    companies: int  # distinct company names among scraped jobs/questions
    discovered_companies: int  # rows in the companies table (PHASE7.md step 5) — a
    # different count on purpose: a company can be discovered without a single
    # job scraped from it yet, and `companies` above counts scraped jobs/
    # questions' own `company` text field, not this table at all.
    escalation_rate: float  # fraction of saved items that needed the frontier tier


def get_run(session: Session, run_id: int) -> Run | None:
    return session.get(Run, run_id)


def list_runs(session: Session, *, limit: int, offset: int) -> tuple[list[Run], int]:
    """Return one page of runs, newest first, plus the total count."""
    return _paginate(session, select(Run).order_by(Run.id.desc()), limit, offset)


def _job_query(
    *,
    company: str | None,
    source: str | None,
    q: str | None,
    starred: bool | None,
    status: str | None,
) -> Select[tuple[Job]]:
    query = select(Job).order_by(Job.id.desc())
    if company:
        query = query.where(Job.company.ilike(f"%{company}%"))
    if source:
        query = query.where(Job.source == source)
    if q:
        query = query.where(Job.title.ilike(f"%{q}%"))
    if starred is not None:
        query = query.where(Job.starred == starred)
    if status:
        query = query.where(Job.status == status)
    return query


def list_jobs(
    session: Session,
    *,
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
    status: str | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Job], int]:
    """Return one page of jobs (newest first) matching the filters, plus the total."""
    query = _job_query(company=company, source=source, q=q, starred=starred, status=status)
    return _paginate(session, query, limit, offset)


def export_jobs(
    session: Session,
    *,
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
    status: str | None = None,
) -> Iterator[Job]:
    """Every job matching the filters, no pagination — for CSV/JSON export.

    Deliberately lazy (PHASE9.md step 8), not `.all()` into a list: the
    real, unbounded-memory risk lived in materializing every matching row
    at once before this — the caller (api/export.py's streaming helpers)
    keeps this session open only as long as it's actually iterating,
    mirroring stream.py's existing session-per-generator pattern for
    GET /runs/stream, the only other place in this app that already
    solved "session must outlive a generator-driven response."""
    query = _job_query(company=company, source=source, q=q, starred=starred, status=status)
    return iter(session.scalars(query))


def set_job_starred(session: Session, job_id: int, starred: bool) -> Job | None:
    """Flip a job's starred flag; returns None when it doesn't exist."""
    job = session.get(Job, job_id)
    if job is None:
        return None
    job.starred = starred
    session.commit()
    return job


def set_job_status(session: Session, job_id: int, status: str) -> Job | None:
    """Move a job to a new pipeline status (PHASE8.md step 2); returns None
    when it doesn't exist. Records status_changed_at on every real
    transition, including back to "none" — a job that was applied to and
    then reset is a real, worth-recording event, not silently indistinguishable
    from one that was never touched."""
    job = session.get(Job, job_id)
    if job is None:
        return None
    job.status = status
    job.status_changed_at = datetime.now(UTC)
    session.commit()
    return job


def _question_query(
    *,
    company: str | None,
    round_: str | None,
    q: str | None,
) -> Select[tuple[InterviewQuestion]]:
    query = select(InterviewQuestion).order_by(InterviewQuestion.id.desc())
    if company:
        query = query.where(InterviewQuestion.company.ilike(f"%{company}%"))
    if round_:
        query = query.where(InterviewQuestion.round == round_)
    if q:
        query = query.where(InterviewQuestion.question.ilike(f"%{q}%"))
    return query


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
    return _paginate(session, _question_query(company=company, round_=round_, q=q), limit, offset)


def export_questions(
    session: Session,
    *,
    company: str | None = None,
    round_: str | None = None,
    q: str | None = None,
) -> Iterator[InterviewQuestion]:
    """Every question matching the filters, no pagination — for CSV/JSON
    export. Deliberately lazy, same reasoning as export_jobs above."""
    return iter(session.scalars(_question_query(company=company, round_=round_, q=q)))


def compute_stats(session: Session) -> Stats:
    """Compute the dashboard totals in one place, so routes stay logic-free."""
    jobs = _count(session, select(Job))
    questions = _count(session, select(InterviewQuestion))
    # Null company (PHASE3.md step 4 — generic question banks) doesn't count
    # as a "company" in the distinct-companies total.
    companies_union = select(Job.company).union(
        select(InterviewQuestion.company).where(InterviewQuestion.company.is_not(None))
    )
    companies = _count(session, companies_union)
    discovered_companies = _count(session, select(Company))
    frontier = _count(session, select(Job).where(Job.extraction_tier == "frontier")) + _count(
        session, select(InterviewQuestion).where(InterviewQuestion.extraction_tier == "frontier")
    )
    total = jobs + questions
    rate = frontier / total if total else 0.0
    return Stats(
        jobs=jobs,
        questions=questions,
        companies=companies,
        discovered_companies=discovered_companies,
        escalation_rate=rate,
    )


def _paginate[T](
    session: Session, query: Select[tuple[T]], limit: int, offset: int
) -> tuple[list[T], int]:
    total = _count(session, query)
    rows = session.scalars(query.limit(limit).offset(offset)).all()
    return list(rows), total


def _count[T](session: Session, query: Select[tuple[T]] | CompoundSelect[tuple[T]]) -> int:
    return session.scalar(select(func.count()).select_from(query.subquery())) or 0
