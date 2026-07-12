"""SSE polling/diffing for GET /runs/stream (PHASE6.md step 6) and
GET /applications/{id}/stream (PHASE14.md step 4).

Kept separate from routes.py so the route handler stays thin — same
separation as export.py for CSV serialization.
"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.api.application_view import to_application_out
from backend.api.dto import RunList, RunOut
from backend.api.dto_applications import ApplicationDetail, ApplicationEventOut
from backend.autoapply import events
from backend.db import repo
from backend.db.models import Application

POLL_INTERVAL_S = 1.0
STREAM_LIMIT = 20


def _run_list_payload(engine: Engine) -> str:
    """The same {items, total} shape GET /runs returns, as a JSON string."""
    with Session(engine) as session:
        runs, total = repo.list_runs(session, limit=STREAM_LIMIT, offset=0)
        body = RunList(items=[RunOut.model_validate(run) for run in runs], total=total)
    return body.model_dump_json()


async def run_updates(engine: Engine, request: Request) -> AsyncIterator[str]:
    """Yield one SSE frame each time the runs list actually changes.

    Polls the DB every ~1s on a worker thread (run_in_threadpool, so the
    blocking SQLAlchemy call never stalls the event loop) — simpler and
    less invasive than threading a pub/sub through repo.finish_run /
    record_error; revisit only if 1s polling turns out to feel laggy.
    """
    last: str | None = None
    while not await request.is_disconnected():
        payload = await run_in_threadpool(_run_list_payload, engine)
        if payload != last:
            last = payload
            yield f"data: {payload}\n\n"
        await asyncio.sleep(POLL_INTERVAL_S)


def _application_detail_payload(engine: Engine, application_id: int) -> str | None:
    """The same {application, events} shape GET /applications/{id}
    returns, as a JSON string — None if the application doesn't exist,
    so the caller can end the stream instead of polling forever."""
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if application is None:
            return None
        log = events.list_events(session, application)
        body = ApplicationDetail(
            application=to_application_out(session, application),
            events=[ApplicationEventOut.model_validate(event) for event in log],
        )
    return body.model_dump_json()


async def application_updates(
    engine: Engine, request: Request, application_id: int
) -> AsyncIterator[str]:
    """Yield one SSE frame each time this application's detail payload
    actually changes — same diff-based polling shape as run_updates,
    parameterized by application_id instead of the fixed runs list."""
    last: str | None = None
    while not await request.is_disconnected():
        payload = await run_in_threadpool(_application_detail_payload, engine, application_id)
        if payload is None:
            return
        if payload != last:
            last = payload
            yield f"data: {payload}\n\n"
        await asyncio.sleep(POLL_INTERVAL_S)
