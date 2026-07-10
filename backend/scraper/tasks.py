"""Huey wiring: one task, `run_scrape_task`, that both manual (`POST /runs`,
PHASE5.md step 1) and scheduled (`dispatch_due_schedule`, PHASE5.md step 2)
runs enqueue. `SqliteHuey` needs zero extra services — a sibling file to
`hirable.db`, not sharing a connection with SQLAlchemy. Calling
`run_scrape_task(run_id)` enqueues it; the actual execution happens on the
`huey.consumer.Consumer` thread started by `create_app` (`api/main.py`), not
in the calling request/thread.
"""

from datetime import UTC, datetime

from huey import SqliteHuey, crontab
from huey.consumer import Consumer
from sqlalchemy.orm import Session

from backend.db import backup, repo
from backend.scraper.discovery import discover_and_save_companies
from backend.scraper.pipeline import build_embedder, build_extractor, build_fetcher, execute_run
from backend.scraper.resolve import resolve_unresolved_companies

huey = SqliteHuey("hirable", filename="huey.db")


@huey.task()  # type: ignore[untyped-decorator]  # huey ships no stubs
def run_scrape_task(run_id: int) -> None:
    """Execute an already-created run — mirrors the session-per-cycle
    pattern the old scheduler.py used, since the consumer thread can't share
    the request-scoped session the API used to create the run. The row's
    own `model` (PHASE6.md step 3) travels with it, so this reads whichever
    model the run was actually created with rather than always the default."""
    engine = repo.make_engine()
    with Session(engine) as session:
        run = repo.get_run(session, run_id)
        if run is None:  # pragma: no cover - the row was just created
            return
        execute_run(
            session,
            run,
            build_fetcher(run.source),
            build_extractor(run.model),
            embed=build_embedder(),
        )


@huey.task()  # type: ignore[untyped-decorator]  # huey ships no stubs
def run_scrape_batch_item(kind: str, source: str, model: str) -> None:
    """One step of a multi-select batch pipeline (PHASE5.md step 3) — unlike
    run_scrape_task, creates its own run row lazily right as this step
    executes (mirrors pipeline.run_scrape's create-then-execute pattern), so
    only one run is ever "running" at a time even while later sources in the
    batch are still queued behind it. Must return None: execute_run's own
    broad except (DESIGN.md §3) already turns any per-run failure into a
    "failed" status rather than a raised exception — if that ever changed,
    a raised exception here would stop the rest of the pipeline dead
    (verified: Huey does not continue a .then() chain past a failed step)."""
    engine = repo.make_engine()
    with Session(engine) as session:
        run = repo.create_run(session, kind, source, model=model)
        execute_run(
            session, run, build_fetcher(source), build_extractor(model), embed=build_embedder()
        )


def enqueue_batch(kind: str, sources: list[str], model: str) -> None:
    """Chain one run_scrape_batch_item per source into a single pipeline,
    enqueued once — sources run strictly in order, one at a time, all with
    the same chosen model (PHASE6.md step 3)."""
    pipeline = run_scrape_batch_item.s(kind, sources[0], model)
    for source in sources[1:]:
        pipeline = pipeline.then(run_scrape_batch_item, kind, source, model)
    huey.enqueue(pipeline)


@huey.task()  # type: ignore[untyped-decorator]  # huey ships no stubs
def run_company_discovery_task(source: str) -> None:
    """Discover + resolve for one company source (PHASE8.md step 7) — no
    `Run` row: that shape (pages_fetched, items_saved, extraction_tier
    stats) is built around the LLM-extraction pipeline, and a discovery
    pass is a genuinely different kind of work. Discovery and resolution
    both happen in the same tick — this is the scheduled equivalent of a
    user clicking "Discover" then "Resolve" in the UI, not two separate
    schedules."""
    engine = repo.make_engine()
    with Session(engine) as session:
        discover_and_save_companies(session, source)
        resolve_unresolved_companies(session)


@huey.periodic_task(crontab(minute="*"))  # type: ignore[untyped-decorator]  # huey ships no stubs
def dispatch_due_schedule(now: datetime | None = None) -> None:
    """Runs once a minute on the consumer's own scheduler — replaces the old
    scheduler.py poll loop's job, but dispatches through Huey instead of
    executing inline. `now` defaults to the real current time; tests inject
    a fixed one.

    A "companies" schedule dispatches to run_company_discovery_task, not
    the Run-row pipeline (PHASE8.md step 7) — and is deliberately not
    gated behind active_run_exists the way a jobs/questions schedule is:
    company discovery/resolution hits different domains
    (ycombinator.com, Wikipedia, Greenhouse/Lever) than whatever
    job/question source might be actively scraping, and is far cheaper
    than an LLM-extraction run, so there's no real reason to block it."""
    engine = repo.make_engine()
    with Session(engine) as session:
        now = now or datetime.now(UTC)
        due = repo.due_schedules(session, now)
        if not due:
            return
        schedule = due[0]  # others wait for the next minute's tick
        if schedule.kind == "companies":
            run_company_discovery_task(schedule.source)
            repo.mark_schedule_run(session, schedule, now)
            return
        if repo.active_run_exists(session):
            return
        run = repo.create_run(session, schedule.kind, schedule.source)
        run_scrape_task(run.id)
        repo.mark_schedule_run(session, schedule, now)


@huey.periodic_task(crontab(hour="3", minute="0"))  # type: ignore[untyped-decorator]  # huey ships no stubs
def create_database_backup() -> None:
    """Real SQLite backup (PHASE9.md step 5), once daily — a Huey periodic
    task, the same unattended-background pattern every other scheduled
    behavior in this app already uses, not a manual script the user has
    to remember to run (which would just recreate the exact "no real
    backup happens" gap this closes). Same caveat as every other
    crontab-scheduled task here: only fires while the app happens to be
    running at that hour — accepted, not solved differently, since that's
    already true of dispatch_due_schedule too."""
    backup.create_backup()


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
