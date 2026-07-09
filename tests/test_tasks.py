"""Tests for Huey task wiring — no network, no LLM (CLAUDE.md).

call_local() runs a task's function body synchronously, bypassing the
queue/consumer entirely — exactly what a unit test wants.
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.db import repo
from backend.db.models import Base, Run
from backend.scraper import tasks
from backend.scraper.tasks import run_scrape_task

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def engine() -> Engine:
    # StaticPool: run_scrape_task opens its own Session on its own engine
    # (mirrors run_scheduler_loop's session-per-cycle pattern) — this must
    # share the same in-memory DB the test set up, not get a fresh empty one.
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def test_run_scrape_task_executes_existing_run(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    with Session(engine) as session:
        run = repo.create_run(session, kind="jobs", source="hn")
        run_id = run.id

    calls: list[int] = []

    def fake_execute_run(session: Session, run: Run, fetcher: object, extractor: object) -> Run:
        calls.append(run.id)
        repo.finish_run(session, run)
        return run

    monkeypatch.setattr(tasks, "execute_run", fake_execute_run)

    run_scrape_task.call_local(run_id)

    assert calls == [run_id]
    with Session(engine) as session:
        finished = repo.get_run(session, run_id)
        assert finished is not None
        assert finished.status == "completed"


def test_run_scrape_task_missing_run_does_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    calls: list[int] = []
    monkeypatch.setattr(tasks, "execute_run", lambda *a: calls.append(1))  # noqa: ARG005

    run_scrape_task.call_local(999)

    assert calls == []


def _fake_run_scrape_task(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    monkeypatch.setattr(tasks, "run_scrape_task", lambda run_id: calls.append(run_id))
    return calls


def test_dispatch_due_schedule_no_schedules_does_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    calls = _fake_run_scrape_task(monkeypatch)

    tasks.dispatch_due_schedule.call_local(now=NOW)

    assert calls == []


def test_dispatch_due_schedule_starts_a_run_and_marks_last_run_at(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    calls = _fake_run_scrape_task(monkeypatch)
    with Session(engine) as session:
        repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)

    tasks.dispatch_due_schedule.call_local(now=NOW)

    assert len(calls) == 1
    with Session(engine) as session:
        schedule = repo.list_schedules(session)[0]
        assert schedule.last_run_at == NOW.replace(tzinfo=None)


def test_dispatch_due_schedule_not_yet_due_is_skipped(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    calls = _fake_run_scrape_task(monkeypatch)
    with Session(engine) as session:
        schedule = repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
        repo.mark_schedule_run(session, schedule, NOW)

    tasks.dispatch_due_schedule.call_local(now=NOW + timedelta(hours=1))

    assert calls == []


def test_dispatch_due_schedule_active_run_blocks(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    calls = _fake_run_scrape_task(monkeypatch)
    with Session(engine) as session:
        repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
        repo.create_run(session, kind="jobs", source="hn")  # already running

    tasks.dispatch_due_schedule.call_local(now=NOW)

    assert calls == []


def test_dispatch_due_schedule_only_one_of_several_due_starts(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tasks.repo, "make_engine", lambda: engine)
    calls = _fake_run_scrape_task(monkeypatch)
    with Session(engine) as session:
        repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
        repo.create_schedule(session, kind="questions", source="hn-interviews", every_hours=24)

    tasks.dispatch_due_schedule.call_local(now=NOW)

    assert len(calls) == 1
