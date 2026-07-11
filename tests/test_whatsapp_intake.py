"""Tests for single-URL job intake (PHASE13.md step 11) — no network, no
LLM (CLAUDE.md); Fetcher/Extractor are faked, same precedent
test_pipeline.py already sets."""

import json

import pytest
from sqlalchemy.orm import Session

from backend.db import repo
from backend.scraper.extractor import Extractor
from backend.scraper.fetcher import FetchError, Page, PageFetcher
from backend.scraper.pipeline import ExtractSchema
from backend.whatsapp.intake import extract_urls, intake_job_link


class ScriptedClient:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    def complete(self, prompt: str, *, schema: dict | None = None) -> str:
        return self._responses.pop(0)


class FakeFetcher(PageFetcher):
    def __init__(self, outcomes: dict[str, Page | Exception]) -> None:
        super().__init__()
        self._outcomes = outcomes

    def fetch(self, url: str) -> Page:
        outcome = self._outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def job_json(title: str) -> str:
    item = {
        "title": title,
        "company": "Acme",
        "location": None,
        "salary": None,
        "requirements": [],
        "apply_url": None,
    }
    return json.dumps({"items": [item]})


def extractor_with(responses: list[str]) -> Extractor[ExtractSchema]:
    return Extractor[ExtractSchema](ScriptedClient(responses), frontier=None)


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


def test_extract_urls_finds_every_real_url_in_a_message() -> None:
    text = "found two: https://a.com/job/1 and https://b.com/job/2, check them out"
    assert extract_urls(text) == ["https://a.com/job/1", "https://b.com/job/2,"]


def test_extract_urls_returns_empty_for_a_plain_message() -> None:
    assert extract_urls("hey, how's the job search going?") == []


def test_intake_job_link_saves_a_real_job_and_completes_the_run(session: Session) -> None:
    url = "https://example.com/job/1"
    fetcher = FakeFetcher({url: Page(url=url, markdown="", raw="<p>Backend role</p>")})
    extractor = extractor_with([job_json("Backend Engineer")])

    saved = intake_job_link(session, url, fetcher, extractor)

    assert saved is True
    runs = repo.list_runs(session, limit=10, offset=0)[0]
    assert len(runs) == 1
    assert runs[0].source == "whatsapp"
    assert runs[0].status == "completed"


def test_intake_job_link_records_a_failed_run_on_fetch_error(session: Session) -> None:
    url = "https://example.com/job/broken"
    fetcher = FakeFetcher({url: FetchError("timeout")})
    extractor = extractor_with([])

    saved = intake_job_link(session, url, fetcher, extractor)

    assert saved is False
    run = repo.list_runs(session, limit=10, offset=0)[0][0]
    assert run.status == "failed"
    assert run.errors == [{"url": url, "error": "timeout"}]


def test_intake_job_link_records_a_failed_run_on_extraction_failure(session: Session) -> None:
    url = "https://example.com/job/garbage"
    fetcher = FakeFetcher({url: Page(url=url, markdown="", raw="<p>not real json</p>")})
    extractor = extractor_with(["not json at all", "still not json"])

    saved = intake_job_link(session, url, fetcher, extractor)

    assert saved is False
    run = repo.list_runs(session, limit=10, offset=0)[0][0]
    assert run.status == "failed"


def test_intake_job_link_is_a_no_op_duplicate_on_a_known_posting_url(session: Session) -> None:
    url = "https://example.com/job/1"
    fetcher = FakeFetcher({url: Page(url=url, markdown="", raw="<p>Backend role</p>")})

    first = intake_job_link(session, url, fetcher, extractor_with([job_json("Backend Engineer")]))
    second = intake_job_link(session, url, fetcher, extractor_with([job_json("Backend Engineer")]))

    assert first is True
    assert second is False  # already stored — save_job's own dedupe, not re-extracted differently
