"""Tests for the Himalayas source."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

LONG_DESCRIPTION = (
    "We build developer tools for distributed systems. You will design APIs, "
    "review pull requests, and mentor junior engineers on a small remote team."
)


def himalayas_response(offset: int = 0, limit: int = 20, total: int = 1) -> str:
    return json.dumps(
        {
            "offset": offset,
            "limit": limit,
            "totalCount": total,
            "jobs": [
                {
                    "title": "Backend Engineer",
                    "companyName": "Acme Robotics",
                    "locationRestrictions": ["Germany"],
                    "minSalary": 60000,
                    "maxSalary": 90000,
                    "currency": "EUR",
                    "salaryPeriod": "annual",
                    "description": f"<p>{LONG_DESCRIPTION}</p>",
                    "applicationLink": "https://himalayas.app/companies/acme/jobs/backend-engineer",
                },
                {
                    "title": "Gardener",
                    "companyName": "Ghar",
                    "description": "Short.",
                    "applicationLink": "https://himalayas.app/companies/ghar/jobs/gardener",
                },
                {
                    "title": "No URL Role",
                    "companyName": "X",
                    "description": LONG_DESCRIPTION,
                    "applicationLink": "",
                },
            ],
        }
    )


def himalayas_page(raw: str | None = None) -> Page:
    return Page(url=seed_urls("himalayas")[0], markdown="", raw=raw or himalayas_response())


def test_seed_url_is_the_public_api() -> None:
    assert seed_urls("himalayas") == ["https://himalayas.app/jobs/api?limit=20&offset=0"]


def test_split_items_chunks_listings_with_own_url() -> None:
    chunks = split_items(himalayas_page(), "himalayas")
    assert len(chunks) == 1
    assert chunks[0].url == "https://himalayas.app/companies/acme/jobs/backend-engineer"
    assert "Backend Engineer at Acme Robotics" in chunks[0].text
    assert "distributed systems" in chunks[0].text


def test_split_items_skips_short_and_urlless_listings() -> None:
    chunks = split_items(himalayas_page(), "himalayas")
    urls = [chunk.url for chunk in chunks]
    assert "https://himalayas.app/companies/ghar/jobs/gardener" not in urls  # too short
    assert all("No URL" not in chunk.text for chunk in chunks)


def test_next_links_computes_offset_from_response_fields() -> None:
    page = himalayas_page(himalayas_response(offset=0, limit=20, total=45))
    assert next_links(page, "himalayas") == ["https://himalayas.app/jobs/api?limit=20&offset=20"]


def test_next_links_empty_on_last_page() -> None:
    page = himalayas_page(himalayas_response(offset=20, limit=20, total=30))
    assert next_links(page, "himalayas") == []


def test_malformed_payload_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not a Himalayas"):
        split_items(himalayas_page(json.dumps({"not": "expected"})), "himalayas")
    with pytest.raises(ValueError):
        split_items(himalayas_page("{{{ not json"), "himalayas")
