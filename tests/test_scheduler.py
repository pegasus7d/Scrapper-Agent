"""Tests for the schedule polling cycle — no network, no LLM, no real sleep."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper import scheduler
from backend.scraper.extractor import Extractor
from backend.scraper.fetcher import PageFetcher
from backend.scraper.pipeline import ExtractSchema
from backend.scraper.scheduler import run_due_schedules

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


def fake_run_scrape_calls(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Records (kind, source) for each call and finishes the run cleanly."""
    calls: list[tuple[str, str]] = []

    def fake(session: Session, kind: str, source: str, fetcher: object, extractor: object) -> None:
        calls.append((kind, source))
        run = repo.create_run(session, kind, source)
        repo.finish_run(session, run)

    monkeypatch.setattr(scheduler, "run_scrape", fake)
    return calls


def build_extractor() -> Extractor[ExtractSchema]:
    raise AssertionError("build_extractor should not be called when nothing is due")


def fetcher_factory(source: str) -> PageFetcher:
    return PageFetcher()


def test_no_schedules_does_nothing(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_run_scrape_calls(monkeypatch)
    run_due_schedules(session, fetcher_factory, build_extractor, NOW)
    assert calls == []


def test_due_schedule_starts_a_run_and_marks_last_run_at(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_run_scrape_calls(monkeypatch)
    repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    run_due_schedules(session, fetcher_factory, lambda: object(), NOW)  # type: ignore[arg-type]
    assert calls == [("jobs", "hn")]
    assert repo.list_schedules(session)[0].last_run_at == NOW.replace(tzinfo=None)


def test_not_yet_due_schedule_is_skipped(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_run_scrape_calls(monkeypatch)
    schedule = repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    repo.mark_schedule_run(session, schedule, NOW)
    run_due_schedules(session, fetcher_factory, build_extractor, NOW + timedelta(hours=1))
    assert calls == []


def test_active_run_blocks_starting_a_due_schedule(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_run_scrape_calls(monkeypatch)
    repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    repo.create_run(session, kind="jobs", source="hn")  # already running
    run_due_schedules(session, fetcher_factory, build_extractor, NOW)
    assert calls == []


def test_only_one_of_several_due_schedules_starts_per_cycle(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = fake_run_scrape_calls(monkeypatch)
    repo.create_schedule(session, kind="jobs", source="hn", every_hours=6)
    repo.create_schedule(session, kind="questions", source="hn-interviews", every_hours=24)
    run_due_schedules(session, fetcher_factory, lambda: object(), NOW)  # type: ignore[arg-type]
    assert len(calls) == 1


def test_scheduler_loop_stops_after_one_iteration_via_sleep_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies the loop calls run_due_schedules and then sleeps, every cycle."""
    engine = repo.make_engine("sqlite:///:memory:")
    cycles: list[None] = []
    monkeypatch.setattr(
        scheduler,
        "run_due_schedules",
        lambda *a, **k: cycles.append(None),  # noqa: ARG005
    )

    def sleep_and_stop(seconds: float) -> None:
        if len(cycles) >= 2:
            raise SystemExit

    with pytest.raises(SystemExit):
        scheduler.run_scheduler_loop(engine, lambda: object(), sleep=sleep_and_stop)  # type: ignore[arg-type]
    assert len(cycles) == 2
