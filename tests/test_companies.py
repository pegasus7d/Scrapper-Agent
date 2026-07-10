"""Tests for discovered-company CRUD (PHASE7.md step 5)."""

import pytest
from sqlalchemy.orm import Session

from backend.db import repo


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def test_save_company_inserts_new(session: Session) -> None:
    saved = repo.save_company(session, "DoorDash")
    assert saved is True
    names = [c.name for c in repo.list_companies(session)]
    assert names == ["DoorDash"]


def test_save_company_dedupes_by_name(session: Session) -> None:
    repo.save_company(session, "DoorDash")
    saved_again = repo.save_company(session, "DoorDash")
    assert saved_again is False
    assert len(repo.list_companies(session)) == 1


def test_list_companies_newest_first(session: Session) -> None:
    repo.save_company(session, "First")
    repo.save_company(session, "Second")
    names = [c.name for c in repo.list_companies(session)]
    assert names == ["Second", "First"]


def test_unresolved_companies_excludes_resolved(session: Session) -> None:
    repo.save_company(session, "Resolved")
    repo.save_company(session, "Unresolved")
    resolved = repo.list_companies(session)[1]
    assert resolved.name == "Resolved"
    repo.mark_company_checked(session, resolved, slug="resolved", ats_provider="greenhouse")

    unresolved = [c.name for c in repo.unresolved_companies(session)]
    assert unresolved == ["Unresolved"]


def test_mark_company_checked_sets_last_checked_at_even_without_a_match(
    session: Session,
) -> None:
    repo.save_company(session, "Unresolved")
    company = repo.list_companies(session)[0]
    repo.mark_company_checked(session, company)

    session.refresh(company)
    assert company.last_checked_at is not None
    assert company.ats_provider is None
    assert company in repo.unresolved_companies(session)


def test_mark_company_checked_records_a_real_match(session: Session) -> None:
    repo.save_company(session, "Airbnb")
    company = repo.list_companies(session)[0]
    repo.mark_company_checked(session, company, slug="airbnb", ats_provider="greenhouse")

    session.refresh(company)
    assert company.slug == "airbnb"
    assert company.ats_provider == "greenhouse"
    assert company not in repo.unresolved_companies(session)
