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
    resolved.ats_provider = "greenhouse"
    session.commit()

    unresolved = [c.name for c in repo.unresolved_companies(session)]
    assert unresolved == ["Unresolved"]
