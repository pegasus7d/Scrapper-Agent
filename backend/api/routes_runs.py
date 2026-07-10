"""Run and schedule endpoints — split from routes.py to stay under
CLAUDE.md's 300-line file cap (PHASE9.md step 3), proactively rather than
reactively this time: `routes_companies.py`/`routes_resume.py` were both
split only after routes.py had already crossed the cap. Runs and schedules
share this file because a schedule's only real job is to eventually kick
off a run — `_SOURCES_BY_KIND` and the discovery-source validation both
serve `POST /runs`/`POST /runs/batch` and `POST /schedules` alike.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import Engine

from backend import config
from backend.api.deps import LimitParam, OffsetParam, SessionDep
from backend.api.dto import (
    BatchQueued,
    Cancelled,
    RunBatchRequest,
    RunCreated,
    RunList,
    RunOut,
    RunRequest,
    ScheduleOut,
    ScheduleRequest,
    ToggleRequest,
)
from backend.api.stream import run_updates
from backend.db import repo
from backend.llm.client import list_local_models
from backend.scraper.discovery import DISCOVERY_SOURCES
from backend.scraper.sources import JOB_SOURCES, QUESTION_SOURCES
from backend.scraper.tasks import enqueue_batch, run_scrape_task

router = APIRouter()

_SOURCES_BY_KIND = {"jobs": JOB_SOURCES, "questions": QUESTION_SOURCES}


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


@router.get("/schedules")
def list_schedules(session: SessionDep) -> list[ScheduleOut]:
    return [ScheduleOut.model_validate(s) for s in repo.list_schedules(session)]


@router.post("/schedules", status_code=201)
def create_schedule(body: ScheduleRequest, session: SessionDep) -> ScheduleOut:
    if body.kind == "companies":
        if body.source not in DISCOVERY_SOURCES:
            raise HTTPException(422, f"unknown discovery source: {body.source}")
    elif body.source not in _SOURCES_BY_KIND[body.kind]:
        raise HTTPException(422, f"unknown source for {body.kind}: {body.source}")
    schedule = repo.create_schedule(session, body.kind, body.source, body.every_hours)
    return ScheduleOut.model_validate(schedule)


@router.post("/schedules/{schedule_id}/toggle")
def toggle_schedule(schedule_id: int, body: ToggleRequest, session: SessionDep) -> ScheduleOut:
    schedule = repo.set_schedule_enabled(session, schedule_id, body.enabled)
    if schedule is None:
        raise HTTPException(404, "schedule not found")
    return ScheduleOut.model_validate(schedule)
