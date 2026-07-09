"""Tests for the scrape loop — no network, no LLM (CLAUDE.md); all fakes."""

import json
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend import config
from backend.db import repo
from backend.db.models import Job, Run
from backend.llm.client import FrontierClient
from backend.schemas import JobExtract, QuestionExtract
from backend.scraper import pipeline
from backend.scraper.extractor import Extractor
from backend.scraper.fetcher import FetchError, Page, PageFetcher
from backend.scraper.pipeline import ExtractSchema, build_extractor, build_fetcher, run_scrape
from backend.scraper.sources import Chunk
from backend.scraper.transport import HttpxTransport, ScraplingTransport

LISTING = "https://l.com/listing"
GARBAGE = "not json at all"


class ScriptedClient:
    """LLMClient fake returning queued responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses

    def complete(self, prompt: str, *, schema: dict | None = None) -> str:
        return self._responses.pop(0)


class FakeFetcher(PageFetcher):
    """Returns or raises scripted outcomes per URL, recording every fetch."""

    def __init__(self, outcomes: dict[str, Page | Exception]) -> None:
        super().__init__()
        self._outcomes = outcomes
        self.fetched: list[str] = []

    def fetch(self, url: str) -> Page:
        self.fetched.append(url)
        outcome = self._outcomes[url]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def page(url: str) -> Page:
    return Page(url=url, markdown="text", raw="{}")


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


def fake_sources(
    seeds: list[str],
    chunks: dict[str, list[Chunk]] | None = None,
    links: dict[str, list[str]] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        seed_urls=lambda source: list(seeds),
        split_items=lambda page, source: (chunks or {}).get(page.url, []),
        next_links=lambda page, source: (links or {}).get(page.url, []),
        delay_for=lambda source: 0.0,
    )


@pytest.fixture
def session() -> Session:
    return Session(repo.make_engine("sqlite:///:memory:"))


@pytest.fixture(autouse=True)
def local_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pipeline, "ollama_available", lambda: True)


def scrape(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
    *,
    sources: SimpleNamespace,
    fetcher: FakeFetcher,
    extractor: Extractor[ExtractSchema] | None = None,
) -> Run:
    monkeypatch.setattr(pipeline, "sources", sources)
    return run_scrape(
        session, "jobs", "hn", fetcher, extractor or extractor_with([]), sleep=lambda s: None
    )


def test_happy_path_saves_items_and_completes_run(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    world = fake_sources([LISTING], chunks={LISTING: [Chunk("acme ad", "https://l.com/i/1")]})
    run = scrape(
        session,
        monkeypatch,
        sources=world,
        fetcher=FakeFetcher({LISTING: page(LISTING)}),
        extractor=extractor_with([job_json("Backend Engineer")]),
    )
    assert run.status == "completed"
    assert (run.pages_fetched, run.items_saved, run.errors) == (1, 1, [])


def test_many_chunks_save_items_with_distinct_posting_urls(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = [Chunk(f"ad {n}", f"https://l.com/i/{n}") for n in (1, 2, 3)]
    world = fake_sources([LISTING], chunks={LISTING: chunks})
    run = scrape(
        session,
        monkeypatch,
        sources=world,
        fetcher=FakeFetcher({LISTING: page(LISTING)}),
        extractor=extractor_with([job_json(f"Role {n}") for n in (1, 2, 3)]),
    )
    urls = set(session.scalars(select(Job.posting_url)))
    assert run.items_saved == 3
    assert urls == {"https://l.com/i/1", "https://l.com/i/2", "https://l.com/i/3"}


def test_failed_chunk_recorded_and_remaining_chunks_processed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = [Chunk("bad ad", "https://l.com/i/1"), Chunk("good ad", "https://l.com/i/2")]
    world = fake_sources([LISTING], chunks={LISTING: chunks})
    run = scrape(
        session,
        monkeypatch,
        sources=world,
        fetcher=FakeFetcher({LISTING: page(LISTING)}),
        # First chunk exhausts both local attempts; second parses fine.
        extractor=extractor_with([GARBAGE, GARBAGE, job_json("Role")]),
    )
    assert run.status == "completed"
    assert run.items_saved == 1
    assert [error["url"] for error in run.errors] == ["https://l.com/i/1"]


def test_fetch_error_recorded_and_loop_continues(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    good = "https://l.com/2"
    world = fake_sources([LISTING, good], chunks={good: [Chunk("ad", "https://l.com/i/1")]})
    fetcher = FakeFetcher({LISTING: FetchError("HTTP 404"), good: page(good)})
    run = scrape(
        session,
        monkeypatch,
        sources=world,
        fetcher=fetcher,
        extractor=extractor_with([job_json("Role")]),
    )
    assert run.status == "completed"
    assert run.items_saved == 1
    assert run.errors == [{"url": LISTING, "error": "HTTP 404"}]


def test_max_pages_per_run_stops_the_loop(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline.config, "MAX_PAGES_PER_RUN", 2)
    urls = [f"https://l.com/{n}" for n in (1, 2, 3)]
    world = fake_sources([urls[0]], links={urls[0]: [urls[1]], urls[1]: [urls[2]]})
    fetcher = FakeFetcher({url: page(url) for url in urls})
    run = scrape(session, monkeypatch, sources=world, fetcher=fetcher)
    assert run.status == "completed"
    assert run.pages_fetched == 2
    assert fetcher.fetched == urls[:2]


def test_visited_urls_are_not_refetched(session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    # The rediscovered link only differs by a tracking param — same page.
    world = fake_sources([LISTING], links={LISTING: [f"{LISTING}?utm_source=x"]})
    fetcher = FakeFetcher({LISTING: page(LISTING)})
    run = scrape(session, monkeypatch, sources=world, fetcher=fetcher)
    assert run.status == "completed"
    assert fetcher.fetched == [LISTING]


def test_cancel_request_stops_loop_with_cancelled_status(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    urls = ["https://l.com/1", "https://l.com/2"]
    world = fake_sources(urls)
    fetcher = FakeFetcher({url: page(url) for url in urls})

    def cancel_during_sleep(seconds: float) -> None:
        assert repo.request_cancel(session, run_id=1)

    monkeypatch.setattr(pipeline, "sources", world)
    run = run_scrape(session, "jobs", "hn", fetcher, extractor_with([]), sleep=cancel_during_sleep)
    assert run.status == "cancelled"
    assert fetcher.fetched == [urls[0]]  # second URL never fetched


def test_known_chunk_url_skips_extraction_entirely(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    known = "https://l.com/i/1"
    with_run = repo.create_run(session, kind="jobs", source="hn")
    repo.save_job(
        session,
        JobExtract(
            title="Old", company="Acme", location=None, salary=None, requirements=[], apply_url=None
        ),
        posting_url=known,
        source="hn",
        tier="local",
        run=with_run,
    )
    repo.finish_run(session, with_run)

    world = fake_sources([LISTING], chunks={LISTING: [Chunk("seen ad", known)]})
    # extractor_with([]) raises if the LLM is ever called — the run would fail.
    run = scrape(session, monkeypatch, sources=world, fetcher=FakeFetcher({LISTING: page(LISTING)}))
    assert run.status == "completed"
    assert run.items_duplicate == 1
    assert run.items_saved == 0


def test_known_question_source_url_skips_extraction(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    known = "https://l.com/c/9"
    with_run = repo.create_run(session, kind="questions", source="hn-interviews")
    repo.save_question(
        session,
        QuestionExtract(company="Acme", role=None, question="Design a cache.", round=None),
        source_url=known,
        source="hn-interviews",
        tier="local",
        run=with_run,
    )
    repo.finish_run(session, with_run)

    world = fake_sources([LISTING], chunks={LISTING: [Chunk("seen comment", known)]})
    monkeypatch.setattr(pipeline, "sources", world)
    run = run_scrape(
        session,
        "questions",
        "hn-interviews",
        FakeFetcher({LISTING: page(LISTING)}),
        extractor_with([]),
        sleep=lambda s: None,
    )
    assert run.status == "completed"
    assert run.items_duplicate == 1


def test_cancel_mid_page_stops_remaining_chunks(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = [Chunk("ad 1", "https://l.com/i/1"), Chunk("ad 2", "https://l.com/i/2")]
    world = fake_sources([LISTING], chunks={LISTING: chunks})

    class CancellingClient:
        """Cancels the run while the first chunk is being extracted."""

        def complete(self, prompt: str, *, schema: dict | None = None) -> str:
            assert repo.request_cancel(session, run_id=1)
            return job_json("Role")

    run = scrape(
        session,
        monkeypatch,
        sources=world,
        fetcher=FakeFetcher({LISTING: page(LISTING)}),
        extractor=Extractor[ExtractSchema](CancellingClient(), frontier=None),
    )
    assert run.status == "cancelled"
    assert run.items_saved == 1  # first chunk finished, second never started


def test_malformed_payload_recorded_and_loop_continues(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def bad_split(page: Page, source: str) -> list[Chunk]:
        raise ValueError("malformed payload")

    world = fake_sources([LISTING])
    world.split_items = bad_split
    run = scrape(session, monkeypatch, sources=world, fetcher=FakeFetcher({LISTING: page(LISTING)}))
    assert run.status == "completed"
    assert run.errors == [{"url": LISTING, "error": "malformed payload"}]


def test_ollama_unreachable_fails_run_before_fetching(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "ollama_available", lambda: False)
    fetcher = FakeFetcher({})
    run = scrape(session, monkeypatch, sources=fake_sources([LISTING]), fetcher=fetcher)
    assert run.status == "failed"
    assert run.errors == [{"url": "", "error": "ollama unreachable"}]
    assert fetcher.fetched == []


def test_unexpected_crash_marks_run_failed(
    session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = scrape(
        session,
        monkeypatch,
        sources=fake_sources([LISTING]),
        fetcher=FakeFetcher({LISTING: RuntimeError("boom")}),
    )
    assert run.status == "failed"
    assert run.errors == [{"url": "", "error": "boom"}]


def test_unknown_kind_raises(session: Session) -> None:
    with pytest.raises(ValueError, match="unknown kind"):
        run_scrape(session, "resumes", "hn", FakeFetcher({}), extractor_with([]))


def test_build_extractor_without_api_key_disables_escalation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline.config, "anthropic_api_key", lambda: None)
    assert build_extractor()._frontier is None


def test_build_extractor_with_api_key_enables_frontier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline.config, "anthropic_api_key", lambda: "sk-test")
    assert isinstance(build_extractor()._frontier, FrontierClient)


def test_build_fetcher_defaults_to_httpx_transport() -> None:
    fetcher = build_fetcher("hn")
    assert isinstance(fetcher._transport, HttpxTransport)
    assert fetcher._delay_s == config.REQUEST_DELAY_S


def test_build_fetcher_honors_a_source_forced_onto_scrapling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(pipeline.sources, "transport_for", lambda source: "scrapling")
    assert isinstance(build_fetcher("hn")._transport, ScraplingTransport)


def test_build_fetcher_honors_arbeitnows_doubled_delay() -> None:
    assert build_fetcher("arbeitnow")._delay_s == config.REQUEST_DELAY_S * 2
