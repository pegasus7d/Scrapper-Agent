"""SSE polling/diffing for GET /runs/stream (PHASE6.md step 6).

Kept separate from routes.py so the route handler stays thin — same
separation as export.py for CSV serialization.
"""

import asyncio
from collections.abc import AsyncIterator

from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.api.dto import RunList, RunOut
from backend.db import repo

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
