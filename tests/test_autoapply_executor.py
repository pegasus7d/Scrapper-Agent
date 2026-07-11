"""Tests for the confirmed-application executor (PHASE11.md step 7) — a
real, live HTTP server (uvicorn in a background thread) serving
test_form_server's real, fully-working form, driven by a real headless
browser. Only ever run against the local test-form server — never a
real, live ATS; this module is the only one in the project that can
cause a real submission, and this project's own build/test loop never
points it at a real target.
"""

import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
import uvicorn
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import events, executor, safety, test_form_server
from backend.db import repo
from backend.db.models import Application, Company, Job
from backend.schemas import JobExtract

_PORT = 8926
_URL = f"http://127.0.0.1:{_PORT}"


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


@pytest.fixture(autouse=True)
def _resume_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    destination = tmp_path / "resume.pdf"
    destination.write_bytes(b"%PDF-1.4 fake but real bytes for upload_file")
    monkeypatch.setattr(config, "RESUME_STORAGE_PATH", str(destination))


def _make_company(session: Session, *, ats_provider: str | None = "lever") -> Company:
    company = Company(name="Acme", ats_provider=ats_provider, discovered_at=datetime.now(UTC))
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
    repo.save_job(session, extract, posting_url=posting_url, source="hn", tier="local", run=run)
    job_id = session.scalar(select(Job.id).where(Job.posting_url == posting_url))
    assert job_id is not None
    job = session.get(Job, job_id)
    assert job is not None
    return job


_FULL_PLAN = [
    {
        "field_name": "full_name",
        "label": "Full name",
        "input_type": "text",
        "answer": "Ada Lovelace",
        "source": "profile",
    },
    {
        "field_name": "email",
        "label": "Email address",
        "input_type": "email",
        "answer": "ada@example.com",
        "source": "profile",
    },
    {
        "field_name": "phone",
        "label": "Phone number",
        "input_type": "tel",
        "answer": "555-0100",
        "source": "profile",
    },
    {
        "field_name": "role",
        "label": "Role applying for",
        "input_type": "",
        "answer": "backend",
        "source": "profile",
    },
    {
        "field_name": "resume",
        "label": "Resume",
        "input_type": "file",
        "answer": "resume-backend.pdf",
        "source": "profile",
    },
    {
        "field_name": "cover_note",
        "label": "Anything else you'd like us to know?",
        "input_type": "",
        "answer": "Real executor test.",
        "source": "llm",
    },
    {
        "field_name": "relocate",
        "label": None,
        "input_type": "radio",
        "answer": "Yes",
        "source": "profile",
    },
    {
        "field_name": "remote_ok",
        "label": "Open to fully remote roles",
        "input_type": "checkbox",
        "answer": "true",
        "source": "profile",
    },
]


def _make_awaiting_confirmation_application(
    session: Session, company: Company, job: Job, *, planned_fields: list | None = None
) -> Application:
    application = events.start_application(session, company_id=company.id, job_id=job.id)
    events.mark_awaiting_confirmation(
        session, application, risk_level="high", planned_fields=planned_fields or _FULL_PLAN
    )
    return application


def test_execute_submission_refuses_when_not_awaiting_confirmation(session: Session) -> None:
    company = _make_company(session)
    job = _make_job(session, company, posting_url=_URL)
    application = events.start_application(session, company_id=company.id, job_id=job.id)
    with pytest.raises(executor.NotAwaitingConfirmation):
        executor.execute_submission(session, application)


def test_execute_submission_refuses_when_not_confirmed(session: Session) -> None:
    company = _make_company(session)
    job = _make_job(session, company, posting_url=_URL)
    application = _make_awaiting_confirmation_application(session, company, job)
    with pytest.raises(executor.NotConfirmed):
        executor.execute_submission(session, application)


def test_execute_submission_refuses_when_kill_switch_is_on(session: Session) -> None:
    company = _make_company(session)
    job = _make_job(session, company, posting_url=_URL)
    application = _make_awaiting_confirmation_application(session, company, job)
    events.record_event(session, application, action="confirm", success=True)
    safety.set_kill_switch(session, True)
    with pytest.raises(safety.KillSwitchActive):
        executor.execute_submission(session, application)


def test_execute_submission_marks_failed_on_drift(session: Session, live_form_server: None) -> None:
    company = _make_company(session)
    job = _make_job(session, company, posting_url=_URL)
    drifted_plan = [
        {
            "field_name": "a_field_that_does_not_exist",
            "label": None,
            "input_type": "text",
            "answer": "x",
            "source": "profile",
        }
    ]
    application = _make_awaiting_confirmation_application(
        session, company, job, planned_fields=drifted_plan
    )
    events.record_event(session, application, action="confirm", success=True)

    executor.execute_submission(session, application)

    assert application.status == "failed"
    assert application.error is not None
    assert "drift" in application.error


def test_execute_submission_real_happy_path_fills_and_submits(
    session: Session, live_form_server: None
) -> None:
    company = _make_company(session)
    job = _make_job(session, company, posting_url=_URL)
    application = _make_awaiting_confirmation_application(session, company, job)
    events.record_event(session, application, action="confirm", success=True)

    executor.execute_submission(session, application)

    assert application.status == "submitted"
    assert application.finished_at is not None
    assert application.error is None

    log = events.list_events(session, application)
    assert any(e.action == "submit" and e.success for e in log)
    assert any(e.action == "fill_field:full_name" and e.success for e in log)
