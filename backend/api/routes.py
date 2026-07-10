"""Endpoint handlers — thin by design: parse, call repo/pipeline, shape response.

Request/response models live in dto.py; every response goes through one of
them (DESIGN.md §4). List endpoints return {items, total} with ?limit=
(default 20, max 100) and ?offset=.

Run and schedule endpoints live in routes_runs.py, not here — split
proactively (PHASE9.md step 3) before this file re-crossed the 300-line
cap, mirroring the existing routes_companies.py/routes_resume.py splits.
"""

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import text

from backend.api.deps import LimitParam, OffsetParam, SessionDep
from backend.api.dto import (
    HealthOut,
    JobList,
    JobOut,
    ModelOut,
    QuestionList,
    QuestionOut,
    StarRequest,
    StatsOut,
    StatusRequest,
)
from backend.api.export import (
    stream_jobs_csv,
    stream_jobs_json,
    stream_questions_csv,
    stream_questions_json,
)
from backend.db import repo, search
from backend.db.models import JOB_STATUSES
from backend.llm.client import list_local_models
from backend.llm.embeddings import embed_text

ExportFormat = Literal["csv", "json"]

logger = logging.getLogger(__name__)

router = APIRouter()


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


@router.get("/health")
def health(request: Request, session: SessionDep) -> HealthOut:
    """Real status (PHASE9.md step 6), not a bare 200 — the app now runs
    unattended background work (Huey's scheduler ticks once a minute), so
    "is it actually alive" needs an answer that doesn't depend on hitting
    an unrelated business endpoint and hoping it doesn't fail for a
    different reason. A health check's whole job is to report failure, not
    raise it — broad except is the correct, deliberate choice here (same
    justification execute_run's own broad except uses, DESIGN.md §3), not
    swallowed-by-accident."""
    try:
        session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:
        logger.warning("health check: database unreachable", exc_info=True)
        database_ok = False
    thread = request.app.state.consumer_thread
    huey_consumer_ok = thread is not None and thread.is_alive()
    return HealthOut(database=database_ok, huey_consumer=huey_consumer_ok)


@router.get("/models")
def list_models() -> list[ModelOut]:
    return [ModelOut(name=m.name, size_bytes=m.size_bytes) for m in list_local_models()]


@router.get("/jobs")
def list_jobs(
    session: SessionDep,
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
    status: str | None = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> JobList:
    jobs, total = repo.list_jobs(
        session,
        company=company,
        source=source,
        q=q,
        starred=starred,
        status=status,
        limit=limit,
        offset=offset,
    )
    return JobList(items=[JobOut.model_validate(job) for job in jobs], total=total)


@router.post("/jobs/{job_id}/star")
def star_job(job_id: int, body: StarRequest, session: SessionDep) -> JobOut:
    job = repo.set_job_starred(session, job_id, body.starred)
    if job is None:
        raise HTTPException(404, "job not found")
    return JobOut.model_validate(job)


@router.post("/jobs/{job_id}/status")
def status_job(job_id: int, body: StatusRequest, session: SessionDep) -> JobOut:
    """Move a job through the application pipeline (PHASE8.md step 2) —
    never a client-supplied string passed straight through unchecked, same
    discipline _resolve_model uses for locally-installed model names."""
    if body.status not in JOB_STATUSES:
        raise HTTPException(422, f"unknown status: {body.status}")
    job = repo.set_job_status(session, job_id, body.status)
    if job is None:
        raise HTTPException(404, "job not found")
    return JobOut.model_validate(job)


@router.get("/jobs/export")
def export_jobs(
    request: Request,
    format: ExportFormat = "json",
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
    status: str | None = None,
) -> StreamingResponse:
    """Streams rows as they're fetched (PHASE9.md step 8), not a full list
    materialized in memory first — takes `request` (for `app.state.engine`)
    instead of `SessionDep`, since a StreamingResponse's body is sent after
    the route handler function returns, by which point a request-scoped
    session dependency has already closed; the streaming helper opens its
    own short-lived session instead (see api/export.py's own docstring)."""
    engine = request.app.state.engine
    if format == "csv":
        return StreamingResponse(
            stream_jobs_csv(
                engine, company=company, source=source, q=q, starred=starred, status=status
            ),
            media_type="text/csv",
            headers=_attachment("jobs.csv"),
        )
    return StreamingResponse(
        stream_jobs_json(
            engine, company=company, source=source, q=q, starred=starred, status=status
        ),
        media_type="application/json",
        headers=_attachment("jobs.json"),
    )


@router.get("/questions")
def list_questions(
    session: SessionDep,
    company: str | None = None,
    round: str | None = None,
    q: str | None = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> QuestionList:
    questions, total = repo.list_questions(
        session, company=company, round_=round, q=q, limit=limit, offset=offset
    )
    items = [QuestionOut.model_validate(question) for question in questions]
    return QuestionList(items=items, total=total)


@router.get("/questions/export")
def export_questions(
    request: Request,
    format: ExportFormat = "json",
    company: str | None = None,
    round: str | None = None,
    q: str | None = None,
) -> StreamingResponse:
    """Streams rows as they're fetched (PHASE9.md step 8) — see
    export_jobs's own docstring for why this takes `request` instead of
    `SessionDep`."""
    engine = request.app.state.engine
    if format == "csv":
        return StreamingResponse(
            stream_questions_csv(engine, company=company, round_=round, q=q),
            media_type="text/csv",
            headers=_attachment("questions.csv"),
        )
    return StreamingResponse(
        stream_questions_json(engine, company=company, round_=round, q=q),
        media_type="application/json",
        headers=_attachment("questions.json"),
    )


@router.get("/stats")
def get_stats(session: SessionDep) -> StatsOut:
    stats = repo.compute_stats(session)
    return StatsOut(
        jobs=stats.jobs,
        questions=stats.questions,
        companies=stats.companies,
        discovered_companies=stats.discovered_companies,
        escalation_rate=stats.escalation_rate,
    )


@router.get("/search")
def search_items(
    session: SessionDep, q: str, kind: Literal["jobs", "questions"], limit: LimitParam = 20
) -> JobList | QuestionList:
    """Hybrid search (PHASE6.md step 8): embeds `q` once, then merges a
    sqlite-vec similarity query and an FTS5 keyword query via reciprocal
    rank fusion (backend/db/search.py)."""
    if not q.strip():
        raise HTTPException(422, "q must not be empty")
    embedding = embed_text(q)
    if kind == "jobs":
        jobs = search.search_jobs(session, q, embedding, limit)
        return JobList(items=[JobOut.model_validate(j) for j in jobs], total=len(jobs))
    questions = search.search_questions(session, q, embedding, limit)
    return QuestionList(
        items=[QuestionOut.model_validate(item) for item in questions], total=len(questions)
    )
