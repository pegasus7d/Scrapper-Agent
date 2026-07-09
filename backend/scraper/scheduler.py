"""Background scheduler: starts due scrapes on their own thread (PHASE2.md step 6).

One poll cycle (`run_due_schedules`) is the unit under test; `run_scheduler_loop`
just wraps it in an infinite, sleep-driven loop for the app factory to launch
as a daemon thread. Same best-effort concurrency guard as the API layer
(`active_run_exists` before creating a run) — good enough for a single-user
local tool, not a distributed-lock problem.
"""

import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper.extractor import Extractor
from backend.scraper.fetcher import PageFetcher
from backend.scraper.pipeline import ExtractSchema, build_fetcher, run_scrape

logger = logging.getLogger(__name__)

DEFAULT_POLL_SECONDS = 60


def run_due_schedules(
    session: Session,
    build_fetcher: Callable[[str], PageFetcher],
    build_extractor: Callable[[], Extractor[ExtractSchema]],
    now: datetime,
) -> None:
    """Start at most one due schedule's run, if nothing else is already running."""
    if repo.active_run_exists(session):
        return
    due = repo.due_schedules(session, now)
    if not due:
        return
    schedule = due[0]  # others wait for the next poll cycle
    logger.info("schedule %s due: starting %s/%s", schedule.id, schedule.kind, schedule.source)
    run_scrape(
        session, schedule.kind, schedule.source, build_fetcher(schedule.source), build_extractor()
    )
    repo.mark_schedule_run(session, schedule, now)


def run_scheduler_loop(
    engine: Engine,
    build_extractor: Callable[[], Extractor[ExtractSchema]],
    poll_seconds: int = DEFAULT_POLL_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Poll forever; intended to run as a daemon thread started by the app factory."""
    while True:
        try:
            with Session(engine) as session:
                run_due_schedules(session, build_fetcher, build_extractor, datetime.now(UTC))
        except Exception:  # the scheduler must never die from one bad cycle
            logger.exception("scheduler cycle failed")
        sleep(poll_seconds)
