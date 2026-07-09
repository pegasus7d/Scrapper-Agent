"""Tests for the Arbeitnow source."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

LONG_DESCRIPTION = (
    "We build developer tools for distributed systems. You will design APIs, "
    "review pull requests, and mentor junior engineers on a small remote team."
)


def arbeitnow_response(next_url: str | None = None) -> str:
    return json.dumps(
        {
            "data": [
                {
                    "slug": "acme-backend-engineer",
                    "title": "Backend Engineer",
                    "company_name": "Acme Robotics",
                    "location": "Berlin",
                    "remote": True,
                    "job_types": ["Full-time"],
                    "description": f"<p>{LONG_DESCRIPTION}</p>",
                    "url": "https://www.arbeitnow.com/jobs/companies/acme/backend-engineer",
                },
                {
                    "slug": "ghar-gardener",
                    "title": "Gardener",
                    "company_name": "Ghar",
                    "description": "Short.",
                    "url": "https://www.arbeitnow.com/jobs/companies/ghar/gardener",
                },
                {
                    "slug": "no-url-role",
                    "title": "No URL Role",
                    "company_name": "X",
                    "description": LONG_DESCRIPTION,
                    "url": "",
                },
            ],
            "links": {"next": next_url},
        }
    )


def arbeitnow_page(raw: str | None = None) -> Page:
    return Page(url=seed_urls("arbeitnow")[0], markdown="", raw=raw or arbeitnow_response())


def test_seed_url_is_the_public_api() -> None:
    assert seed_urls("arbeitnow") == ["https://www.arbeitnow.com/api/job-board-api"]


def test_split_items_chunks_listings_with_own_url() -> None:
    chunks = split_items(arbeitnow_page(), "arbeitnow")
    assert len(chunks) == 1
    assert chunks[0].url == "https://www.arbeitnow.com/jobs/companies/acme/backend-engineer"
    assert "Backend Engineer at Acme Robotics" in chunks[0].text
    assert "distributed systems" in chunks[0].text


def test_split_items_skips_short_and_urlless_listings() -> None:
    urls = [chunk.url for chunk in split_items(arbeitnow_page(), "arbeitnow")]
    assert "https://www.arbeitnow.com/jobs/companies/ghar/gardener" not in urls  # too short
    assert all("No URL" not in chunk.text for chunk in split_items(arbeitnow_page(), "arbeitnow"))


def test_next_links_follows_pagination() -> None:
    next_url = "https://www.arbeitnow.com/api/job-board-api?page=2"
    page = arbeitnow_page(arbeitnow_response(next_url=next_url))
    assert next_links(page, "arbeitnow") == [next_url]


def test_next_links_empty_on_last_page() -> None:
    assert next_links(arbeitnow_page(), "arbeitnow") == []


def test_malformed_payload_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not an Arbeitnow"):
        split_items(arbeitnow_page(json.dumps({"not": "expected"})), "arbeitnow")
    with pytest.raises(ValueError):
        split_items(arbeitnow_page("{{{ not json"), "arbeitnow")
