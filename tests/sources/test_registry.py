"""Tests for the Source registry's own dispatch behavior (PHASE3.md step 1)."""

import pytest

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources import (
    JOB_SOURCES,
    QUESTION_SOURCES,
    delay_for,
    next_links,
    seed_urls,
    split_items,
    transport_for,
)

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
