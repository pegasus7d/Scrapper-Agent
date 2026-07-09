"""Tests for the Source registry's own dispatch behavior (DESIGN.md §10 step 1)."""

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import (
    JOB_SOURCES,
    QUESTION_SOURCES,
    next_links,
    seed_urls,
    split_items,
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
    assert "hn-interviews" in QUESTION_SOURCES
    assert "github-questions" in QUESTION_SOURCES
