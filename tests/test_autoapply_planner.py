"""Tests for the application-attempt planner (PHASE11.md step 5) — a
real, live HTTP server (uvicorn in a background thread) serving
test_form_server's Greenhouse-like/Lever-like routes, a real headless
browser, and a scripted fake LLMClient (no network, no real Ollama call).
Real live ATS postings are never touched by the permanent test suite
(PHASE10.md step 8's own precedent).
"""

import json
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
import sqlite_vec
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import events, planner, safety, test_form_server
from backend.autoapply.profile import save_profile, save_resume_markdown
from backend.db import repo
from backend.db.models import Company, Job
from backend.schemas import JobExtract
from backend.scraper.extractor import Extractor

_PORT = 8925
_URL = f"http://127.0.0.1:{_PORT}"


class RepeatingClient:
    """Fake LLMClient returning the same response for every call --
    fields differ per test page, so a fixed response queue would need to
    guess the exact count."""

    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, prompt: str, *, schema: dict | None = None) -> str:
        return self._response


def _phone_tool_response() -> str:
    return json.dumps({"items": [{"tool_name": "get_phone", "answer": None}]})


@pytest.fixture(scope="module")
def live_form_server() -> Iterator[None]:
    server_config = uvicorn.Config(
        test_form_server.app, host="127.0.0.1", port=_PORT, log_level="warning"
    )
    server = uvicorn.Server(server_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("test form server did not start in time")
    yield
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


def _vec(nonzero_dims: list[float]) -> bytes:
    padded = nonzero_dims + [0.0] * (config.EMBED_DIM - len(nonzero_dims))
    return sqlite_vec.serialize_float32(padded)


def _make_company(
    session: Session, *, ats_provider: str | None, blocked: bool = False, name: str = "Acme"
) -> Company:
    company = Company(
        name=name,
        ats_provider=ats_provider,
        discovered_at=datetime.now(UTC),
        auto_apply_blocked=blocked,
    )
    session.add(company)
    session.commit()
    return company


def _make_job(session: Session, company: Company, *, posting_url: str) -> Job:
    run = repo.create_run(session, kind="jobs", source="hn")
    extract = JobExtract(
        title="Backend Engineer",
        company=company.name,
        location=None,
        salary=None,
        requirements=["Python"],
        apply_url=None,
    )
    repo.save_job(
        session,
        extract,
        posting_url=posting_url,
        source="hn",
        tier="local",
        run=run,
        embed=lambda _: _vec([1.0, 0.0]),
    )
    job_id = session.scalar(select(Job.id).where(Job.posting_url == posting_url))
    assert job_id is not None
    job = session.get(Job, job_id)
    assert job is not None
    return job


def _set_up_resume(session: Session) -> None:
    save_profile(
        session,
        phone="555-0100",
        current_salary=None,
        expected_salary=None,
        work_authorization=None,
        relocation=None,
        start_date_availability=None,
    )
    save_resume_markdown(session, "Experienced backend engineer skilled in Python.")


@pytest.fixture(autouse=True)
def _fake_embed_and_extractor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.autoapply.matching.embed_text", lambda text: _vec([1.0, 0.0]))
    fake_extractor: Extractor = Extractor(RepeatingClient(_phone_tool_response()), frontier=None)
    monkeypatch.setattr(planner, "build_answer_extractor", lambda: fake_extractor)


def test_plan_application_raises_when_kill_switch_is_on(session: Session) -> None:
    safety.set_kill_switch(session, True)
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/1")
    with pytest.raises(safety.KillSwitchActive):
        planner.plan_application(session, job)


def test_plan_application_raises_for_unresolved_provider(session: Session) -> None:
    company = _make_company(session, ats_provider=None)
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/2")
    with pytest.raises(planner.NoResolvedProvider):
        planner.plan_application(session, job)


def test_plan_application_raises_when_company_is_blocked(session: Session) -> None:
    company = _make_company(session, ats_provider="lever", blocked=True)
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/3")
    with pytest.raises(planner.CompanyBlocked):
        planner.plan_application(session, job)


def test_plan_application_raises_for_a_duplicate_application(session: Session) -> None:
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/4")
    events.start_application(session, company_id=company.id, job_id=job.id)
    with pytest.raises(planner.DuplicateApplication):
        planner.plan_application(session, job)


def test_plan_application_raises_when_daily_cap_reached(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "MAX_APPLICATIONS_PER_DAY", 0)
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/5")
    with pytest.raises(safety.ApplicationCapReached):
        planner.plan_application(session, job)


def test_plan_application_raises_when_pacing_violated(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "MIN_SECONDS_BETWEEN_APPLICATIONS", 300)
    other_company = _make_company(session, ats_provider="lever", name="Other Co")
    events.start_application(session, company_id=other_company.id)

    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/6")
    with pytest.raises(safety.PacingViolation):
        planner.plan_application(session, job)


def test_plan_application_raises_when_no_resume_uploaded(session: Session) -> None:
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/7")
    with pytest.raises(planner.NoResumeUploaded):
        planner.plan_application(session, job)


def test_plan_application_raises_when_match_score_too_low(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("backend.autoapply.matching.embed_text", lambda text: _vec([0.0, 1.0]))
    _set_up_resume(session)
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/8")
    with pytest.raises(planner.MatchScoreTooLow):
        planner.plan_application(session, job)


def test_plan_application_reaches_awaiting_confirmation_with_a_real_plan(
    session: Session, live_form_server: None
) -> None:
    _set_up_resume(session)
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/9")

    application = planner.plan_application(session, job)

    assert application.status == "awaiting_confirmation"
    assert application.risk_level == "high"  # first application to this company
    assert application.finished_at is None  # a real pause, not terminal
    assert len(application.planned_fields) == 1
    planned = application.planned_fields[0]
    assert planned["field_name"] == "name"
    assert planned["answer"] == "555-0100"
    assert planned["source"] == "profile"


def test_plan_application_marks_failed_when_no_fields_detected(session: Session) -> None:
    """A page that never resolves any real form (an unreachable /apply
    path under a real, live server) -- a genuine detection failure, not a
    pre-flight gate rejection."""
    _set_up_resume(session)
    company = _make_company(session, ats_provider="greenhouse")
    job = _make_job(session, company, posting_url="http://127.0.0.1:1")

    application = planner.plan_application(session, job)

    assert application.status == "failed"
    assert application.error is not None


def test_planner_has_no_way_to_fill_or_submit() -> None:
    """A structural guarantee, not just a behavioral one: this module
    never even imports the real fill/submit primitives."""
    assert not hasattr(planner, "fill_field")
    assert not hasattr(planner, "upload_file")
    assert not hasattr(planner, "submit")
    assert not hasattr(planner, "detect_and_fill")
    assert not hasattr(planner, "fill_and_submit")


def test_plan_application_records_every_step_through_the_event_log(
    session: Session, live_form_server: None
) -> None:
    _set_up_resume(session)
    company = _make_company(session, ats_provider="lever")
    job = _make_job(session, company, posting_url=f"{_URL}/lever-like/10")

    application = planner.plan_application(session, job)
    log = events.list_events(session, application)
    assert any(event.action == "answer_field:Full name" for event in log)
    assert all(event.application_id == application.id for event in log)


def test_plan_application_reuses_cached_fields_on_a_repeat_company(
    session: Session, live_form_server: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A second application to the same company's ATS (PHASE12.md step 2)
    must hit the field-detection cache — asserted by counting real calls
    to the live `detect_fields`, not just checking the end result looks
    the same."""
    calls: list[None] = []
    real_detect_fields = planner.detect_fields
    monkeypatch.setattr(
        planner, "detect_fields", lambda page: calls.append(None) or real_detect_fields(page)
    )
    # Two applications back-to-back would otherwise trip the real pacing
    # gate (safety.check_pacing) — irrelevant to what this test verifies.
    monkeypatch.setattr(config, "MIN_SECONDS_BETWEEN_APPLICATIONS", 0)

    _set_up_resume(session)
    company = _make_company(session, ats_provider="lever")
    first_job = _make_job(session, company, posting_url=f"{_URL}/lever-like/30")
    second_job = _make_job(session, company, posting_url=f"{_URL}/lever-like/31")

    first = planner.plan_application(session, first_job)
    second = planner.plan_application(session, second_job)

    assert len(calls) == 1  # live detect_fields ran once, not twice
    assert first.status == second.status == "awaiting_confirmation"
    assert first.planned_fields == second.planned_fields
