"""Tests for ATS slug resolution — no real network (CLAUDE.md); Transport is faked."""

import pytest
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper.resolve import (
    guess_slug,
    resolve_company,
    resolve_unresolved_companies,
)
from backend.scraper.transport import TransportError, TransportResponse


class FakeTransport:
    """status_by_url maps an exact probe URL to the status it should return;
    URLs not present raise TransportError (simulates an unreachable host)."""

    def __init__(self, status_by_url: dict[str, int]) -> None:
        self._status_by_url = status_by_url
        self.calls: list[str] = []

    def get(self, url: str, *, timeout: int, headers: dict[str, str]) -> TransportResponse:
        self.calls.append(url)
        if url not in self._status_by_url:
            raise TransportError("connection refused")
        return TransportResponse(status=self._status_by_url[url], body=b"{}", text="")


def test_guess_slug_strips_spaces_and_case() -> None:
    assert guess_slug("The Athletic") == "theathletic"
    assert guess_slug("DoorDash") == "doordash"
    assert guess_slug("A.B. Co!") == "abco"


def test_resolve_company_hits_greenhouse() -> None:
    transport = FakeTransport({"https://boards-api.greenhouse.io/v1/boards/airbnb/jobs": 200})
    assert resolve_company("Airbnb", transport) == ("airbnb", "greenhouse")


def test_resolve_company_falls_through_to_lever() -> None:
    transport = FakeTransport(
        {
            "https://boards-api.greenhouse.io/v1/boards/theathletic/jobs": 404,
            "https://api.lever.co/v0/postings/theathletic": 200,
        }
    )
    assert resolve_company("The Athletic", transport) == ("theathletic", "lever")


def test_resolve_company_returns_none_on_double_404() -> None:
    transport = FakeTransport(
        {
            "https://boards-api.greenhouse.io/v1/boards/deel/jobs": 404,
            "https://api.lever.co/v0/postings/deel": 404,
        }
    )
    assert resolve_company("Deel", transport) is None
    assert len(transport.calls) == 2


def test_resolve_company_skips_a_transport_error_as_a_miss_not_a_crash() -> None:
    transport = FakeTransport({"https://api.lever.co/v0/postings/deel": 404})
    assert resolve_company("Deel", transport) is None


@pytest.fixture
def session() -> Session:
    engine = repo.make_engine("sqlite:///:memory:")
    return Session(engine)


def test_resolve_unresolved_companies_records_hits_and_misses(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo.save_company(session, "Airbnb")
    repo.save_company(session, "Deel")

    def fake_resolve(name: str) -> tuple[str, str] | None:
        return ("airbnb", "greenhouse") if name == "Airbnb" else None

    monkeypatch.setattr("backend.scraper.resolve.resolve_company", fake_resolve)
    resolved_count = resolve_unresolved_companies(session)

    assert resolved_count == 1
    companies = {c.name: c for c in repo.list_companies(session)}
    assert companies["Airbnb"].ats_provider == "greenhouse"
    assert companies["Deel"].ats_provider is None
    assert companies["Airbnb"].last_checked_at is not None
    assert companies["Deel"].last_checked_at is not None
