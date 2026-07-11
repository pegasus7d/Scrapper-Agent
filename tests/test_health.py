"""Tests for source health checks (PHASE12.md step 1) — no real network
(CLAUDE.md); PageFetcher itself is faked."""

import pytest

from backend.scraper import health as health_module
from backend.scraper.fetcher import FetchError, Page, RobotsDisallowed
from backend.scraper.health import SourceHealth, check_all_sources


class _FakeFetcher:
    def __init__(self, outcome: object) -> None:
        self._outcome = outcome

    def fetch(self, url: str) -> Page:
        if isinstance(self._outcome, Exception):
            raise self._outcome
        return Page(url=url, markdown="ok", raw="ok")


def _patch_fetcher(monkeypatch: pytest.MonkeyPatch, outcome: object) -> None:
    monkeypatch.setattr(health_module, "PageFetcher", lambda **kwargs: _FakeFetcher(outcome))


def test_probe_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetcher(monkeypatch, "reachable")
    result = health_module._probe("hn-jobs", "jobs", "https://hn.example/jobs")
    assert result == SourceHealth(name="hn-jobs", kind="jobs", status="ok", detail=None)


def test_probe_blocked_by_robots(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetcher(monkeypatch, RobotsDisallowed("disallowed by robots.txt: https://x.example/y"))
    result = health_module._probe("wwr", "jobs", "https://x.example/y")
    assert result.status == "blocked"
    assert result.detail is not None and "robots.txt" in result.detail


def test_probe_unreachable_on_generic_fetch_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_fetcher(monkeypatch, FetchError("HTTP 500: https://x.example/y"))
    result = health_module._probe("himalayas", "jobs", "https://x.example/y")
    assert result.status == "unreachable"
    assert result.detail == "HTTP 500: https://x.example/y"


class _FakeJobsSource:
    kind = "jobs"

    def seed_urls(self) -> list[str]:
        return ["https://jobs.example/a"]


class _FakeQuestionsSource:
    kind = "questions"

    def seed_urls(self) -> list[str]:
        return ["https://questions.example/a"]


def test_check_all_sources_covers_jobs_questions_and_discovery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetcher(monkeypatch, "reachable")
    monkeypatch.setattr(
        health_module.sources,
        "SOURCES",
        {"fake-jobs": _FakeJobsSource(), "fake-questions": _FakeQuestionsSource()},
    )
    monkeypatch.setattr(
        health_module.discovery,
        "discovery_seed_urls",
        lambda: [("fake-discovery", "https://discovery.example/a")],
    )

    results = check_all_sources()

    assert {(r.name, r.kind) for r in results} == {
        ("fake-jobs", "jobs"),
        ("fake-questions", "questions"),
        ("fake-discovery", "discovery"),
    }
    assert all(r.status == "ok" for r in results)


def test_check_all_sources_excludes_dynamic_company_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_fetcher(monkeypatch, "reachable")
    monkeypatch.setattr(health_module.sources, "SOURCES", {"company:acme": _FakeJobsSource()})
    monkeypatch.setattr(health_module.discovery, "discovery_seed_urls", lambda: [])

    assert check_all_sources() == []
