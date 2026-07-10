"""FastAPI app factory: engine wiring, stale-run recovery, CORS, router.

Run locally with:  uvicorn --factory backend.api.main:create_app --port 8000
The API binds to localhost and has no auth — it is a local tool (DESIGN.md §4).
"""

import threading

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend import config
from backend.api.routes import router
from backend.api.routes_companies import router as companies_router
from backend.db import repo
from backend.scraper.tasks import run_consumer


def create_app(engine: Engine | None = None, *, start_consumer: bool = True) -> FastAPI:
    """Build the app; tests pass their own engine and disable the consumer thread.

    Scheduled scrapes run via the Huey consumer's own periodic-task scheduler
    (`dispatch_due_schedule`, PHASE5.md step 2) — no separate scheduler thread
    to start here anymore.
    """
    config.configure_logging()
    if engine is None:
        engine = repo.make_engine()
    with Session(engine) as session:
        repo.recover_stale_runs(session)

    app = FastAPI(title="Scraper Agent API")
    app.state.engine = engine
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.CORS_ORIGINS),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api")
    app.include_router(companies_router, prefix="/api")

    if start_consumer:
        threading.Thread(target=run_consumer, daemon=True).start()
    return app
