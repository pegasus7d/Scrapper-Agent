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
from backend.db import repo
from backend.scraper.pipeline import build_extractor
from backend.scraper.scheduler import run_scheduler_loop
from backend.scraper.tasks import run_consumer


def create_app(
    engine: Engine | None = None,
    *,
    start_scheduler: bool = True,
    start_consumer: bool = True,
) -> FastAPI:
    """Build the app; tests pass their own engine and disable both threads."""
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

    if start_scheduler:
        thread = threading.Thread(
            target=run_scheduler_loop, args=(engine, build_extractor), daemon=True
        )
        thread.start()
    if start_consumer:
        threading.Thread(target=run_consumer, daemon=True).start()
    return app
