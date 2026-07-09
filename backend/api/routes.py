"""Endpoint handlers — thin by design: parse, call repo/pipeline, shape response.

Request/response models live in dto.py; every response goes through one of
them (DESIGN.md §4). List endpoints return {items, total} with ?limit=
(default 20, max 100) and ?offset=.
"""

import logging
from collections.abc import Iterator
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend import config
from backend.api.dto import (
    BatchQueued,
    Cancelled,
    JobList,
    JobOut,
    ModelOut,
    QuestionList,
    QuestionOut,
    RunBatchRequest,
    RunCreated,
    RunList,
    RunOut,
    RunRequest,
    ScheduleOut,
    ScheduleRequest,
    StarRequest,
    StatsOut,
    ToggleRequest,
)
from backend.api.export import jobs_to_csv, questions_to_csv
from backend.api.stream import run_updates
from backend.db import repo, search
from backend.llm.client import list_local_models
from backend.llm.embeddings import embed_text
from backend.scraper.sources import JOB_SOURCES, QUESTION_SOURCES
from backend.scraper.tasks import enqueue_batch, run_scrape_task

ExportFormat = Literal["csv", "json"]

logger = logging.getLogger(__name__)

router = APIRouter()

_SOURCES_BY_KIND = {"jobs": JOB_SOURCES, "questions": QUESTION_SOURCES}


def _session(request: Request) -> Iterator[Session]:
    engine: Engine = request.app.state.engine
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(_session)]
LimitParam = Annotated[int, Query(ge=1, le=100)]
OffsetParam = Annotated[int, Query(ge=0)]


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _resolve_model(model: str | None) -> str:
    """None means "use the app default"; otherwise the model must be one
    genuinely installed (PHASE6.md step 3) — never a client-supplied string
    passed straight through to Ollama unchecked."""
    if model is None:
        return config.LOCAL_MODEL
    installed = {m.name for m in list_local_models()}
    if model not in installed:
        raise HTTPException(422, f"model not installed locally: {model}")
    return model


@router.get("/models")
def list_models() -> list[ModelOut]:
    return [ModelOut(name=m.name, size_bytes=m.size_bytes) for m in list_local_models()]


@router.post("/runs", status_code=201)
def start_run(body: RunRequest, session: SessionDep) -> RunCreated:
    if body.source not in _SOURCES_BY_KIND[body.kind]:
        raise HTTPException(422, f"unknown source for {body.kind}: {body.source}")
    model = _resolve_model(body.model)
    if repo.active_run_exists(session):
        raise HTTPException(409, "a run is already active")
    run = repo.create_run(session, body.kind, body.source, model=model)
    run_scrape_task(run.id)  # enqueues onto the Huey consumer, doesn't run inline
    return RunCreated(run_id=run.id)


@router.post("/runs/batch", status_code=202)
def start_run_batch(body: RunBatchRequest, session: SessionDep) -> BatchQueued:
    """Multi-select sources (PHASE5.md step 3) — one Huey pipeline runs them
    one at a time; unlike POST /runs, no run row is created here, since each
    pipeline step lazily creates its own (see run_scrape_batch_item)."""
    for source in body.sources:
        if source not in _SOURCES_BY_KIND[body.kind]:
            raise HTTPException(422, f"unknown source for {body.kind}: {source}")
    model = _resolve_model(body.model)
    if repo.active_run_exists(session):
        raise HTTPException(409, "a run is already active")
    enqueue_batch(body.kind, body.sources, model)
    return BatchQueued(queued=body.sources)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, session: SessionDep) -> Cancelled:
    if not repo.request_cancel(session, run_id):
        raise HTTPException(404, "no active run with this id")
    return Cancelled(cancelled=True)


@router.get("/runs")
def list_runs(session: SessionDep, limit: LimitParam = 20, offset: OffsetParam = 0) -> RunList:
    runs, total = repo.list_runs(session, limit=limit, offset=offset)
    return RunList(items=[RunOut.model_validate(run) for run in runs], total=total)


@router.get("/runs/stream")
def stream_runs(request: Request) -> StreamingResponse:
    """SSE: a frame each time the runs list changes (PHASE6.md step 6),
    same shape as GET /runs — registered before /runs/{run_id} so "stream"
    is never captured as a run_id path parameter."""
    engine: Engine = request.app.state.engine
    return StreamingResponse(run_updates(engine, request), media_type="text/event-stream")


@router.get("/runs/{run_id}")
def get_run(run_id: int, session: SessionDep) -> RunOut:
    run = repo.get_run(session, run_id)
    if run is None:
        raise HTTPException(404, "run not found")
    return RunOut.model_validate(run)


@router.get("/jobs")
def list_jobs(
    session: SessionDep,
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> JobList:
    jobs, total = repo.list_jobs(
        session, company=company, source=source, q=q, starred=starred, limit=limit, offset=offset
    )
    return JobList(items=[JobOut.model_validate(job) for job in jobs], total=total)


@router.post("/jobs/{job_id}/star")
def star_job(job_id: int, body: StarRequest, session: SessionDep) -> JobOut:
    job = repo.set_job_starred(session, job_id, body.starred)
    if job is None:
        raise HTTPException(404, "job not found")
    return JobOut.model_validate(job)


@router.get("/jobs/export")
def export_jobs(
    session: SessionDep,
    format: ExportFormat = "json",
    company: str | None = None,
    source: str | None = None,
    q: str | None = None,
    starred: bool | None = None,
) -> Response:
    jobs = repo.export_jobs(session, company=company, source=source, q=q, starred=starred)
    if format == "csv":
        return PlainTextResponse(
            jobs_to_csv(jobs), media_type="text/csv", headers=_attachment("jobs.csv")
        )
    body = [JobOut.model_validate(job).model_dump(mode="json") for job in jobs]
    return JSONResponse(body, headers=_attachment("jobs.json"))


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
    session: SessionDep,
    format: ExportFormat = "json",
    company: str | None = None,
    round: str | None = None,
    q: str | None = None,
) -> Response:
    questions = repo.export_questions(session, company=company, round_=round, q=q)
    if format == "csv":
        return PlainTextResponse(
            questions_to_csv(questions), media_type="text/csv", headers=_attachment("questions.csv")
        )
    body = [QuestionOut.model_validate(question).model_dump(mode="json") for question in questions]
    return JSONResponse(body, headers=_attachment("questions.json"))


@router.get("/stats")
def get_stats(session: SessionDep) -> StatsOut:
    stats = repo.compute_stats(session)
    return StatsOut(
        jobs=stats.jobs,
        questions=stats.questions,
        companies=stats.companies,
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


@router.get("/schedules")
def list_schedules(session: SessionDep) -> list[ScheduleOut]:
    return [ScheduleOut.model_validate(s) for s in repo.list_schedules(session)]


@router.post("/schedules", status_code=201)
def create_schedule(body: ScheduleRequest, session: SessionDep) -> ScheduleOut:
    if body.source not in _SOURCES_BY_KIND[body.kind]:
        raise HTTPException(422, f"unknown source for {body.kind}: {body.source}")
    schedule = repo.create_schedule(session, body.kind, body.source, body.every_hours)
    return ScheduleOut.model_validate(schedule)


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, body: ToggleRequest, session: SessionDep) -> ScheduleOut:
    schedule = repo.set_schedule_enabled(session, schedule_id, body.enabled)
    if schedule is None:
        raise HTTPException(404, "schedule not found")
    return ScheduleOut.model_validate(schedule)
