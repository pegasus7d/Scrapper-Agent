"""Tests for the Source registry's own dispatch behavior (PHASE3.md step 1)."""

from collections.abc import Iterator

import pytest

from backend import config
from backend.db.models import Company
from backend.scraper.fetcher import Page
from backend.scraper.sources import (
    JOB_SOURCES,
    QUESTION_SOURCES,
    SOURCES,
    company_source_key,
    delay_for,
    next_links,
    register_company_source,
    seed_urls,
    split_items,
    transport_for,
)
from backend.scraper.sources.companies import GreenhouseCompanySource, LeverCompanySource

BLANK_PAGE = Page(url="https://x.com", markdown="", raw="{}")


def test_seed_urls_unknown_source_raises() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        seed_urls("linkedin")


def test_unknown_source_raises_everywhere() -> None:
    with pytest.raises(ValueError, match="unknown source"):
        seed_urls("linkedin")
    with pytest.raises(ValueError, match="unknown source"):
        split_items(BLANK_PAGE, "linkedin")
    with pytest.raises(ValueError, match="unknown source"):
        next_links(BLANK_PAGE, "linkedin")


def test_job_and_question_sources_are_disjoint_and_registered() -> None:
    assert set(JOB_SOURCES) & set(QUESTION_SOURCES) == set()
    assert "hn" in JOB_SOURCES
    assert "remoteok" in JOB_SOURCES
    assert "weworkremotely" in JOB_SOURCES
    assert "arbeitnow" in JOB_SOURCES
    assert "himalayas" in JOB_SOURCES
    assert "remotejobs" in JOB_SOURCES
    assert "hn-interviews" in QUESTION_SOURCES
    assert "github-questions" in QUESTION_SOURCES
    assert "faqguru-questions" in QUESTION_SOURCES


def test_most_sources_default_to_httpx_transport() -> None:
    for source in ("hn", "remoteok", "weworkremotely", "hn-interviews"):
        assert transport_for(source) == "httpx"


def test_most_sources_use_the_global_politeness_delay() -> None:
    for source in ("hn", "remoteok", "weworkremotely", "hn-interviews"):
        assert delay_for(source) == config.REQUEST_DELAY_S


def test_arbeitnow_doubles_the_politeness_delay() -> None:
    # Its own API terms say "please do not abuse" (PHASE4.md step 3).
    assert delay_for("arbeitnow") == config.REQUEST_DELAY_S * 2


def test_github_questions_relaxes_the_politeness_delay() -> None:
    # GitHub's raw CDN has no robots.txt and can take more load (PHASE4.md step 3).
    assert delay_for("github-questions") == config.REQUEST_DELAY_S / 4


def test_faqguru_questions_relaxes_the_politeness_delay() -> None:
    # Same GitHub raw CDN reasoning as github-questions (PHASE5.md step 7).
    assert delay_for("faqguru-questions") == config.REQUEST_DELAY_S / 4


@pytest.fixture
def registered_key() -> Iterator[list[str]]:
    """Company sources land in the shared, module-level SOURCES dict — track
    every key a test registers and remove it afterward so tests don't leak
    into each other."""
    keys: list[str] = []
    yield keys
    for key in keys:
        SOURCES.pop(key, None)


def test_register_company_source_greenhouse(registered_key: list[str]) -> None:
    company = Company(name="Acme", slug="acme", ats_provider="greenhouse")
    key = register_company_source(company)
    registered_key.append(key)
    assert key == "company:acme"
    assert isinstance(SOURCES[key], GreenhouseCompanySource)


def test_register_company_source_lever(registered_key: list[str]) -> None:
    company = Company(name="Acme", slug="acme", ats_provider="lever")
    key = register_company_source(company)
    registered_key.append(key)
    assert key == "company:acme"
    assert isinstance(SOURCES[key], LeverCompanySource)


def test_register_company_source_reflected_in_transport_and_delay_lookups(
    registered_key: list[str],
) -> None:
    company = Company(name="Acme", slug="acme", ats_provider="greenhouse")
    key = register_company_source(company)
    registered_key.append(key)
    assert transport_for(key) == "httpx"
    assert delay_for(key) == config.REQUEST_DELAY_S


def test_register_company_source_rejects_an_unresolved_company() -> None:
    company = Company(name="Acme", slug=None, ats_provider=None)
    with pytest.raises(ValueError, match="not been resolved"):
        register_company_source(company)


def test_register_company_source_rejects_an_unknown_provider() -> None:
    company = Company(name="Acme", slug="acme", ats_provider="workday")
    with pytest.raises(ValueError, match="unknown ATS provider"):
        register_company_source(company)


def test_company_source_key_uses_the_slug() -> None:
    company = Company(name="Acme Inc", slug="acme", ats_provider="greenhouse")
    assert company_source_key(company) == "company:acme"
