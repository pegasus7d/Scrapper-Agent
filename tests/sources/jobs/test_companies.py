"""Tests for company-driven Greenhouse/Lever sources (PHASE7.md step 7)."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources.companies import GreenhouseCompanySource, LeverCompanySource

LONG_DESCRIPTION = (
    "We build developer tools for distributed systems. You will design APIs, "
    "review pull requests, and mentor junior engineers on a small remote team."
)

# Greenhouse's real ?content=true field is double-HTML-escaped: literal
# "&lt;" characters, not real "<" — confirmed against the live API
# (PHASE7.md step 7) before writing this fixture.
_GREENHOUSE_CONTENT = f"&lt;p&gt;{LONG_DESCRIPTION}&lt;/p&gt;"


def greenhouse_response() -> str:
    return json.dumps(
        {
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "absolute_url": "https://careers.acme.com/jobs/1",
                    "location": {"name": "Remote"},
                    "content": _GREENHOUSE_CONTENT,
                },
                {
                    "title": "Short Role",
                    "absolute_url": "https://careers.acme.com/jobs/2",
                    "location": {"name": "Remote"},
                    "content": "&lt;p&gt;Short.&lt;/p&gt;",
                },
                {
                    "title": "No URL Role",
                    "absolute_url": "",
                    "location": {"name": "Remote"},
                    "content": _GREENHOUSE_CONTENT,
                },
            ]
        }
    )


def lever_response() -> str:
    return json.dumps(
        [
            {
                "text": "Backend Engineer",
                "hostedUrl": "https://jobs.lever.co/acme/1",
                "categories": {"location": "Remote"},
                "descriptionPlain": LONG_DESCRIPTION,
            },
            {
                "text": "Short Role",
                "hostedUrl": "https://jobs.lever.co/acme/2",
                "categories": {"location": "Remote"},
                "descriptionPlain": "Short.",
            },
            {
                "text": "No URL Role",
                "hostedUrl": "",
                "categories": {"location": "Remote"},
                "descriptionPlain": LONG_DESCRIPTION,
            },
        ]
    )


def test_greenhouse_seed_url_includes_slug_and_content_flag() -> None:
    source = GreenhouseCompanySource("acme", "Acme")
    assert source.seed_urls() == [
        "https://boards-api.greenhouse.io/v1/boards/acme/jobs?content=true"
    ]


def test_greenhouse_split_items_unescapes_double_encoded_html() -> None:
    source = GreenhouseCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=greenhouse_response())
    chunks = source.split_items(page)
    assert len(chunks) == 1
    assert chunks[0].url == "https://careers.acme.com/jobs/1"
    assert "Backend Engineer at Acme" in chunks[0].text
    assert "distributed systems" in chunks[0].text
    assert "&lt;" not in chunks[0].text  # real unescape, not literal entities


def test_greenhouse_split_items_skips_short_and_urlless() -> None:
    source = GreenhouseCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=greenhouse_response())
    urls = [chunk.url for chunk in source.split_items(page)]
    assert "https://careers.acme.com/jobs/2" not in urls
    assert "" not in urls


def test_greenhouse_next_links_always_empty() -> None:
    source = GreenhouseCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=greenhouse_response())
    assert source.next_links(page) == []


def test_greenhouse_malformed_payload_raises_value_error() -> None:
    source = GreenhouseCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=json.dumps({"not": "expected"}))
    with pytest.raises(ValueError, match="not a Greenhouse"):
        source.split_items(page)


def test_lever_seed_url_includes_slug() -> None:
    source = LeverCompanySource("acme", "Acme")
    assert source.seed_urls() == ["https://api.lever.co/v0/postings/acme?mode=json"]


def test_lever_split_items_builds_real_chunks() -> None:
    source = LeverCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=lever_response())
    chunks = source.split_items(page)
    assert len(chunks) == 1
    assert chunks[0].url == "https://jobs.lever.co/acme/1"
    assert "Backend Engineer at Acme" in chunks[0].text
    assert "distributed systems" in chunks[0].text


def test_lever_split_items_skips_short_and_urlless() -> None:
    source = LeverCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=lever_response())
    urls = [chunk.url for chunk in source.split_items(page)]
    assert "https://jobs.lever.co/acme/2" not in urls
    assert "" not in urls


def test_lever_next_links_always_empty() -> None:
    source = LeverCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=lever_response())
    assert source.next_links(page) == []


def test_lever_malformed_payload_raises_value_error() -> None:
    source = LeverCompanySource("acme", "Acme")
    page = Page(url="x", markdown="", raw=json.dumps({"not": "a list"}))
    with pytest.raises(ValueError, match="not a Lever"):
        source.split_items(page)
