"""Huey wiring: one task, `run_scrape_task`, that both manual (`POST /runs`,
PHASE5.md step 1) and scheduled (`dispatch_due_schedule`, PHASE5.md step 2)
runs enqueue. `SqliteHuey` needs zero extra services — a sibling file to
`scraper.db`, not sharing a connection with SQLAlchemy. Calling
`run_scrape_task(run_id)` enqueues it; the actual execution happens on the
`huey.consumer.Consumer` thread started by `create_app` (`api/main.py`), not
in the calling request/thread.
"""

from datetime import UTC, datetime

from huey import SqliteHuey, crontab
from huey.consumer import Consumer
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper.pipeline import build_extractor, build_fetcher, execute_run

huey = SqliteHuey("scraper-agent", filename="huey.db")


@huey.task()  # type: ignore[untyped-decorator]  # huey ships no stubs
def run_scrape_task(run_id: int) -> None:
    """Execute an already-created run — mirrors the session-per-cycle
    pattern the old scheduler.py used, since the consumer thread can't share
    the request-scoped session the API used to create the run."""
    engine = repo.make_engine()
    with Session(engine) as session:
        run = repo.get_run(session, run_id)
        if run is None:  # pragma: no cover - the row was just created
            return
        execute_run(session, run, build_fetcher(run.source), build_extractor())


@huey.periodic_task(crontab(minute="*"))  # type: ignore[untyped-decorator]  # huey ships no stubs
def dispatch_due_schedule(now: datetime | None = None) -> None:
    """Runs once a minute on the consumer's own scheduler — replaces the old
    scheduler.py poll loop's job, but dispatches through Huey (creates the
    run row, then enqueues run_scrape_task) instead of executing inline.
    Same best-effort concurrency guard as POST /runs (active_run_exists
    before creating a run) — good enough for a single-user local tool.
    `now` defaults to the real current time; tests inject a fixed one."""
    engine = repo.make_engine()
    with Session(engine) as session:
        if repo.active_run_exists(session):
            return
        now = now or datetime.now(UTC)
        due = repo.due_schedules(session, now)
        if not due:
            return
        schedule = due[0]  # others wait for the next minute's tick
        run = repo.create_run(session, schedule.kind, schedule.source)
        run_scrape_task(run.id)
        repo.mark_schedule_run(session, schedule, now)


class _ThreadSafeConsumer(Consumer):  # type: ignore[misc]  # huey ships no stubs; Consumer resolves to Any
    """Consumer.run() calls signal.signal(), which only works on the main
    thread — but this consumer runs on a daemon thread inside the FastAPI
    process, the same lifecycle spot run_scheduler_loop's thread occupies.
    Skip signal registration; uvicorn's own main-thread signal handling
    already covers shutdown for the whole process."""

    def _set_signal_handlers(self) -> None:
        pass


def run_consumer() -> None:
    """Entry point for the daemon thread create_app starts."""
    _ThreadSafeConsumer(huey).run()
