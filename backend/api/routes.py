"""Endpoint handlers — thin by design: parse, call repo/pipeline, shape response.

Every response goes through a Pydantic model (DESIGN.md §4); list endpoints
return {items, total} with ?limit= (default 20, max 100) and ?offset=.
"""

import logging
from collections.abc import Iterator
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper.fetcher import PageFetcher
from backend.scraper.pipeline import build_extractor, execute_run
from backend.scraper.sources import JOB_SOURCES, QUESTION_SOURCES

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


class RunRequest(BaseModel):
    kind: Literal["jobs", "questions"]
    source: str


class RunCreated(BaseModel):
    run_id: int


class Cancelled(BaseModel):
    cancelled: bool


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    source: str
    status: str
    cancel_requested: bool
    started_at: datetime
    finished_at: datetime | None
    pages_fetched: int
    items_saved: int
    items_duplicate: int
    escalations: int
    errors: list[dict[str, str]]


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    company: str
    location: str | None
    salary: str | None
    requirements: list[str]
    posting_url: str
    apply_url: str | None
    source: str
    extraction_tier: str
    scraped_at: datetime


class QuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    company: str
    role: str | None
    question: str
    round: str | None
    source_url: str
    source: str
    extraction_tier: str
    scraped_at: datetime


class RunList(BaseModel):
    items: list[RunOut]
    total: int


class JobList(BaseModel):
    items: list[JobOut]
    total: int


class QuestionList(BaseModel):
    items: list[QuestionOut]
    total: int


class StatsOut(BaseModel):
    jobs: int
    questions: int
    companies: int
    escalation_rate: float


def _execute_in_thread(engine: Engine, run_id: int) -> None:
    """Background half of POST /runs — fresh session, real fetcher and cascade."""
    with Session(engine) as session:
        run = repo.get_run(session, run_id)
        if run is None:  # pragma: no cover - the row was just created
            logger.error("run %s vanished before execution", run_id)
            return
        execute_run(session, run, PageFetcher(), build_extractor())


@router.post("/runs", status_code=201)
def start_run(
    body: RunRequest, background: BackgroundTasks, session: SessionDep, request: Request
) -> RunCreated:
    if body.source not in _SOURCES_BY_KIND[body.kind]:
        raise HTTPException(422, f"unknown source for {body.kind}: {body.source}")
    if repo.active_run_exists(session):
        raise HTTPException(409, "a run is already active")
    run = repo.create_run(session, body.kind, body.source)
    background.add_task(_execute_in_thread, request.app.state.engine, run.id)
    return RunCreated(run_id=run.id)


@router.post("/runs/{run_id}/cancel")
def cancel_run(run_id: int, session: SessionDep) -> Cancelled:
    if not repo.request_cancel(session, run_id):
        raise HTTPException(404, "no active run with this id")
    return Cancelled(cancelled=True)


@router.get("/runs")
def list_runs(session: SessionDep, limit: LimitParam = 20, offset: OffsetParam = 0) -> RunList:
    runs, total = repo.list_runs(session, limit=limit, offset=offset)
    return RunList(items=[RunOut.model_validate(run) for run in runs], total=total)


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
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> JobList:
    jobs, total = repo.list_jobs(
        session, company=company, source=source, q=q, limit=limit, offset=offset
    )
    return JobList(items=[JobOut.model_validate(job) for job in jobs], total=total)


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


@router.get("/stats")
def get_stats(session: SessionDep) -> StatsOut:
    stats = repo.compute_stats(session)
    return StatsOut(
        jobs=stats.jobs,
        questions=stats.questions,
        companies=stats.companies,
        escalation_rate=stats.escalation_rate,
    )
