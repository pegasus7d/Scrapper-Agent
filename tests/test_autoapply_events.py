"""Tests for the application lifecycle + append-only event log (PHASE10.md step 4)."""

import pytest
from sqlalchemy.orm import Session

from backend.autoapply import events
from backend.db import repo
from backend.db.models import Company


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def make_company(session: Session, name: str = "Acme") -> Company:
    repo.save_company(session, name)
    items, _ = repo.list_companies(session)
    return next(c for c in items if c.name == name)


def test_start_application_inserts_a_pending_row(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    assert application.id is not None
    assert application.status == "pending"
    assert application.risk_level == "low"
    assert application.finished_at is None


def test_start_application_records_the_given_risk_level(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id, risk_level="high")
    assert application.risk_level == "high"


def test_finish_application_sets_terminal_status_and_timestamp(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    events.finish_application(session, application, status="submitted")
    assert application.status == "submitted"
    assert application.finished_at is not None
    assert application.error is None


def test_finish_application_records_the_error_on_failure(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    events.finish_application(session, application, status="failed", error="no confirmation page")
    assert application.status == "failed"
    assert application.error == "no confirmation page"


def test_mark_awaiting_confirmation_is_a_real_pause_not_terminal(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    planned = [
        {
            "field_name": "phone",
            "label": "Phone",
            "input_type": "tel",
            "answer": "555-0100",
            "source": "profile",
        }
    ]

    events.mark_awaiting_confirmation(
        session, application, risk_level="high", planned_fields=planned
    )

    assert application.status == "awaiting_confirmation"
    assert application.risk_level == "high"
    assert application.planned_fields == planned
    assert application.finished_at is None  # a real pause, not terminal


def test_record_event_appends_to_the_log(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    events.record_event(session, application, action="detect_fields", success=True)
    events.record_event(session, application, action="fill_field:full_name", success=True)

    log = events.list_events(session, application)
    assert [e.action for e in log] == ["detect_fields", "fill_field:full_name"]
    assert all(e.success for e in log)


def test_record_event_never_overwrites_a_prior_event(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    first = events.record_event(session, application, action="detect_fields", success=True)
    events.record_event(session, application, action="submit", success=False, detail="timeout")

    log = events.list_events(session, application)
    assert len(log) == 2
    assert log[0].id == first.id
    assert log[0].action == "detect_fields"  # untouched by the later, unrelated event


def test_record_event_links_a_retry_to_its_parent(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    failed = events.record_event(
        session, application, action="submit", success=False, detail="timeout"
    )
    retry = events.record_event(
        session, application, action="submit", success=True, parent_event_id=failed.id
    )

    assert retry.parent_event_id == failed.id


def test_list_events_returns_events_oldest_first(session: Session) -> None:
    company = make_company(session)
    application = events.start_application(session, company_id=company.id)
    events.record_event(session, application, action="detect_fields", success=True)
    events.record_event(session, application, action="submit", success=True)

    log = events.list_events(session, application)
    assert [e.action for e in log] == ["detect_fields", "submit"]


def test_list_events_is_scoped_to_one_application(session: Session) -> None:
    company = make_company(session)
    first = events.start_application(session, company_id=company.id)
    second = events.start_application(session, company_id=company.id)
    events.record_event(session, first, action="detect_fields", success=True)
    events.record_event(session, second, action="submit", success=True)

    assert [e.action for e in events.list_events(session, first)] == ["detect_fields"]
    assert [e.action for e in events.list_events(session, second)] == ["submit"]
