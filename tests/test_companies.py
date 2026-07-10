"""Tests for discovered-company CRUD (PHASE7.md step 5, filters PHASE8.md step 1)."""

import pytest
from sqlalchemy.orm import Session

from backend.db import repo
from backend.db.models import Company


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def companies(session: Session) -> list[Company]:
    items, _ = repo.list_companies(session)
    return items


def test_save_company_inserts_new(session: Session) -> None:
    saved = repo.save_company(session, "DoorDash")
    assert saved is True
    names = [c.name for c in companies(session)]
    assert names == ["DoorDash"]


def test_save_company_dedupes_by_name(session: Session) -> None:
    repo.save_company(session, "DoorDash")
    saved_again = repo.save_company(session, "DoorDash")
    assert saved_again is False
    assert len(companies(session)) == 1


def test_list_companies_newest_first(session: Session) -> None:
    repo.save_company(session, "First")
    repo.save_company(session, "Second")
    names = [c.name for c in companies(session)]
    assert names == ["Second", "First"]


def test_list_companies_returns_the_total_independent_of_limit(session: Session) -> None:
    repo.save_company(session, "First")
    repo.save_company(session, "Second")
    items, total = repo.list_companies(session, limit=1)
    assert len(items) == 1
    assert total == 2


def test_list_companies_filters_by_ats_provider(session: Session) -> None:
    repo.save_company(session, "Resolved")
    repo.save_company(session, "Unresolved")
    resolved = companies(session)[1]
    repo.mark_company_checked(session, resolved, slug="resolved", ats_provider="greenhouse")

    items, total = repo.list_companies(session, ats_provider="greenhouse")
    assert [c.name for c in items] == ["Resolved"]
    assert total == 1


def test_list_companies_filters_by_name_substring(session: Session) -> None:
    repo.save_company(session, "DoorDash")
    repo.save_company(session, "Airbnb")
    items, total = repo.list_companies(session, q="door")
    assert [c.name for c in items] == ["DoorDash"]
    assert total == 1


def test_unresolved_companies_excludes_resolved(session: Session) -> None:
    repo.save_company(session, "Resolved")
    repo.save_company(session, "Unresolved")
    resolved = companies(session)[1]
    assert resolved.name == "Resolved"
    repo.mark_company_checked(session, resolved, slug="resolved", ats_provider="greenhouse")

    unresolved = [c.name for c in repo.unresolved_companies(session)]
    assert unresolved == ["Unresolved"]


def test_mark_company_checked_sets_last_checked_at_even_without_a_match(
    session: Session,
) -> None:
    repo.save_company(session, "Unresolved")
    company = companies(session)[0]
    repo.mark_company_checked(session, company)

    session.refresh(company)
    assert company.last_checked_at is not None
    assert company.ats_provider is None
    assert company in repo.unresolved_companies(session)


def test_mark_company_checked_records_a_real_match(session: Session) -> None:
    repo.save_company(session, "Airbnb")
    company = companies(session)[0]
    repo.mark_company_checked(session, company, slug="airbnb", ats_provider="greenhouse")

    session.refresh(company)
    assert company.slug == "airbnb"
    assert company.ats_provider == "greenhouse"
    assert company not in repo.unresolved_companies(session)
