"""Tests for the SSE run-stream generator (PHASE6.md step 6) and the SSE
application-stream generator (PHASE14.md step 4) — no network."""

import asyncio
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from backend.api import stream
from backend.autoapply import events
from backend.db import repo
from backend.db.models import Base, Company


@pytest.fixture
def engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


class FakeRequest:
    """Reports disconnected after `disconnect_after` real poll iterations."""

    def __init__(self, disconnect_after: int) -> None:
        self._remaining = disconnect_after

    async def is_disconnected(self) -> bool:
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False


# Captured before any monkeypatching — stream.asyncio is the same module object.
_real_sleep = asyncio.sleep


def _no_real_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(stream.asyncio, "sleep", lambda _: _real_sleep(0))


async def _collect(engine: Engine, request: FakeRequest) -> list[str]:
    return [frame async for frame in stream.run_updates(engine, request)]  # type: ignore[arg-type]


def test_run_updates_yields_current_state(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_real_sleep(monkeypatch)
    with Session(engine) as session:
        repo.create_run(session, kind="jobs", source="hn")

    frames = asyncio.run(_collect(engine, FakeRequest(disconnect_after=1)))

    assert len(frames) == 1
    assert frames[0].startswith("data: ")
    assert '"total":1' in frames[0]


def test_run_updates_skips_unchanged_polls(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    _no_real_sleep(monkeypatch)
    with Session(engine) as session:
        repo.create_run(session, kind="jobs", source="hn")

    # Three polls, nothing changes between them — only the first should yield.
    frames = asyncio.run(_collect(engine, FakeRequest(disconnect_after=3)))

    assert len(frames) == 1


def test_run_updates_yields_again_when_state_changes(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_real_sleep(monkeypatch)
    with Session(engine) as session:
        run = repo.create_run(session, kind="jobs", source="hn")
        run_id = run.id

    async def drive() -> list[str]:
        frames: list[str] = []
        gen = stream.run_updates(engine, FakeRequest(disconnect_after=2))  # type: ignore[arg-type]
        frames.append(await gen.__anext__())
        with Session(engine) as session:
            changed = repo.get_run(session, run_id)
            assert changed is not None
            repo.finish_run(session, changed)
        async for frame in gen:
            frames.append(frame)
        return frames

    frames = asyncio.run(drive())

    assert len(frames) == 2
    assert '"status":"running"' in frames[0]
    assert '"status":"completed"' in frames[1]


def test_run_updates_stops_when_client_disconnects(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_real_sleep(monkeypatch)
    frames = asyncio.run(_collect(engine, FakeRequest(disconnect_after=0)))
    assert frames == []


async def _collect_application(
    engine: Engine, request: FakeRequest, application_id: int
) -> list[str]:
    return [
        frame
        async for frame in stream.application_updates(engine, request, application_id)  # type: ignore[arg-type]
    ]


def test_application_updates_yields_current_state(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_real_sleep(monkeypatch)
    with Session(engine) as session:
        company = Company(name="Acme", ats_provider="lever", discovered_at=datetime.now(UTC))
        session.add(company)
        session.commit()
        application = events.start_application(session, company_id=company.id)
        application_id = application.id

    frames = asyncio.run(
        _collect_application(engine, FakeRequest(disconnect_after=1), application_id)
    )

    assert len(frames) == 1
    assert frames[0].startswith("data: ")
    assert '"status":"pending"' in frames[0]
    assert '"company_name":"Acme"' in frames[0]


def test_application_updates_skips_unchanged_polls(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_real_sleep(monkeypatch)
    with Session(engine) as session:
        company = Company(name="Acme", ats_provider="lever", discovered_at=datetime.now(UTC))
        session.add(company)
        session.commit()
        application = events.start_application(session, company_id=company.id)
        application_id = application.id

    frames = asyncio.run(
        _collect_application(engine, FakeRequest(disconnect_after=3), application_id)
    )

    assert len(frames) == 1


def test_application_updates_yields_again_when_status_changes(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_real_sleep(monkeypatch)
    with Session(engine) as session:
        company = Company(name="Acme", ats_provider="lever", discovered_at=datetime.now(UTC))
        session.add(company)
        session.commit()
        application = events.start_application(session, company_id=company.id)
        application_id = application.id

    async def drive() -> list[str]:
        frames: list[str] = []
        gen = stream.application_updates(
            engine,
            FakeRequest(disconnect_after=2),
            application_id,  # type: ignore[arg-type]
        )
        frames.append(await gen.__anext__())
        with Session(engine) as session:
            application = session.get(events.Application, application_id)
            assert application is not None
            events.finish_application(session, application, status="rejected")
        async for frame in gen:
            frames.append(frame)
        return frames

    frames = asyncio.run(drive())

    assert len(frames) == 2
    assert '"status":"pending"' in frames[0]
    assert '"status":"rejected"' in frames[1]


def test_application_updates_ends_the_stream_when_application_does_not_exist(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    _no_real_sleep(monkeypatch)
    frames = asyncio.run(
        _collect_application(engine, FakeRequest(disconnect_after=5), application_id=999)
    )
    assert frames == []
