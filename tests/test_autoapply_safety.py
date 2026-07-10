"""Tests for auto-apply safety-control infrastructure (PHASE10.md step 3)."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from backend import config
from backend.autoapply import safety
from backend.db import repo
from backend.db.models import Application, Company


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def make_company(session: Session, name: str = "Acme") -> Company:
    repo.save_company(session, name)
    items, _ = repo.list_companies(session)
    return next(c for c in items if c.name == name)


def make_application(
    session: Session,
    *,
    company: Company,
    job_id: int | None = None,
    started_at: datetime | None = None,
) -> Application:
    application = Application(
        company_id=company.id,
        job_id=job_id,
        started_at=started_at or datetime.now(UTC),
    )
    session.add(application)
    session.commit()
    return application


def test_kill_switch_defaults_off(session: Session) -> None:
    assert safety.kill_switch_enabled(session) is False


def test_kill_switch_can_be_toggled_on_and_off(session: Session) -> None:
    safety.set_kill_switch(session, True)
    assert safety.kill_switch_enabled(session) is True
    safety.set_kill_switch(session, False)
    assert safety.kill_switch_enabled(session) is False


def test_classify_risk_is_high_for_first_application_to_a_company() -> None:
    risk = safety.classify_risk(is_first_application_to_company=True, llm_confidence=0.99)
    assert risk == "high"


def test_classify_risk_is_high_when_confidence_missing() -> None:
    risk = safety.classify_risk(is_first_application_to_company=False, llm_confidence=None)
    assert risk == "high"


def test_classify_risk_is_high_when_confidence_below_threshold() -> None:
    risk = safety.classify_risk(
        is_first_application_to_company=False,
        llm_confidence=config.AUTOAPPLY_LLM_CONFIDENCE_THRESHOLD - 0.01,
    )
    assert risk == "high"


def test_classify_risk_is_low_when_repeat_company_and_confident() -> None:
    risk = safety.classify_risk(
        is_first_application_to_company=False,
        llm_confidence=config.AUTOAPPLY_LLM_CONFIDENCE_THRESHOLD,
    )
    assert risk == "low"


@pytest.mark.parametrize(
    ("policy", "risk_level", "expected"),
    [
        ("always", "low", True),
        ("always", "high", True),
        ("never", "low", False),
        ("never", "high", False),
        ("risky", "low", False),
        ("risky", "high", True),
    ],
)
def test_requires_confirmation_follows_the_configured_policy(
    monkeypatch: pytest.MonkeyPatch, policy: str, risk_level: str, expected: bool
) -> None:
    monkeypatch.setattr(config, "SUBMIT_CONFIRMATION_POLICY", policy)
    assert safety.requires_confirmation(risk_level) is expected


def test_is_company_blocked_reflects_the_flag(session: Session) -> None:
    company = make_company(session)
    assert safety.is_company_blocked(company) is False
    company.auto_apply_blocked = True
    assert safety.is_company_blocked(company) is True


def test_has_existing_application_true_after_one_is_recorded(session: Session) -> None:
    company = make_company(session)
    assert safety.has_existing_application(session, company_id=company.id, job_id=None) is False
    make_application(session, company=company)
    assert safety.has_existing_application(session, company_id=company.id, job_id=None) is True


def test_has_existing_application_is_scoped_by_job_id(session: Session) -> None:
    company = make_company(session)
    make_application(session, company=company, job_id=1)
    assert safety.has_existing_application(session, company_id=company.id, job_id=1) is True
    assert safety.has_existing_application(session, company_id=company.id, job_id=2) is False


def test_applications_started_today_counts_only_todays_rows(session: Session) -> None:
    company = make_company(session)
    make_application(session, company=company, started_at=datetime.now(UTC))
    make_application(session, company=company, started_at=datetime.now(UTC) - timedelta(days=2))
    assert safety.applications_started_today(session) == 1


def test_check_daily_cap_raises_once_the_limit_is_reached(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "MAX_APPLICATIONS_PER_DAY", 1)
    company = make_company(session)
    safety.check_daily_cap(session)  # no applications yet: does not raise
    make_application(session, company=company)
    with pytest.raises(safety.ApplicationCapReached):
        safety.check_daily_cap(session)


def test_stuck_detector_resets_on_success() -> None:
    detector = safety.StuckDetector(max_consecutive_failures=2)
    detector.record(success=False)
    detector.record(success=True)
    detector.record(success=False)
    assert detector.stuck is False


def test_stuck_detector_trips_after_max_consecutive_failures() -> None:
    detector = safety.StuckDetector(max_consecutive_failures=2)
    detector.record(success=False)
    assert detector.stuck is False
    detector.record(success=False)
    assert detector.stuck is True
