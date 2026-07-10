"""Tests for structured applicant profile persistence (PHASE10.md step 5)."""

import pytest
from sqlalchemy.orm import Session

from backend.autoapply import profile
from backend.db import repo


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def test_get_profile_defaults_to_all_unset(session: Session) -> None:
    row = profile.get_profile(session)
    assert row.phone is None
    assert row.current_salary is None
    assert row.expected_salary is None
    assert row.work_authorization is None
    assert row.relocation is None
    assert row.start_date_availability is None


def test_get_profile_is_idempotent(session: Session) -> None:
    first = profile.get_profile(session)
    second = profile.get_profile(session)
    assert first.id == second.id == 1


def test_save_profile_stores_exactly_the_given_values(session: Session) -> None:
    row = profile.save_profile(
        session,
        phone="555-0100",
        current_salary="$120,000",
        expected_salary="$140,000",
        work_authorization="US Citizen",
        relocation=True,
        start_date_availability="2 weeks notice",
    )
    assert row.phone == "555-0100"
    assert row.current_salary == "$120,000"
    assert row.expected_salary == "$140,000"
    assert row.work_authorization == "US Citizen"
    assert row.relocation is True
    assert row.start_date_availability == "2 weeks notice"


def test_save_profile_overwrites_a_prior_save(session: Session) -> None:
    profile.save_profile(
        session,
        phone="555-0100",
        current_salary=None,
        expected_salary=None,
        work_authorization=None,
        relocation=None,
        start_date_availability=None,
    )
    profile.save_profile(
        session,
        phone="555-0200",
        current_salary=None,
        expected_salary=None,
        work_authorization=None,
        relocation=False,
        start_date_availability=None,
    )
    row = profile.get_profile(session)
    assert row.phone == "555-0200"
    assert row.relocation is False
