"""Tests for the RemoteJobs.org source."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

LONG_DESCRIPTION = (
    "We build developer tools for distributed systems. You will design APIs, "
    "review pull requests, and mentor junior engineers on a small remote team."
)


def remotejobs_response(offset: int = 0, limit: int = 20, has_more: bool = False) -> str:
    return json.dumps(
        {
            "data": [
                {
                    "title": "Backend Engineer",
                    "url": "https://remotejobs.org/remote-jobs/acme-backend-engineer",
                    "company": {"name": "Acme Robotics"},
                    "location": "Remote",
                    "type": "Full-time",
                    "description": f"<p>{LONG_DESCRIPTION}</p>",
                },
                {
                    "title": "Gardener",
                    "url": "https://remotejobs.org/remote-jobs/ghar-gardener",
                    "company": {"name": "Ghar"},
                    "description": "Short.",
                },
                {
                    "title": "No URL Role",
                    "url": "",
                    "company": {"name": "X"},
                    "description": LONG_DESCRIPTION,
                },
            ],
            "pagination": {"total": 100, "limit": limit, "offset": offset, "has_more": has_more},
        }
    )


def remotejobs_page(raw: str | None = None) -> Page:
    return Page(url=seed_urls("remotejobs")[0], markdown="", raw=raw or remotejobs_response())


def test_seed_url_is_the_public_api() -> None:
    assert seed_urls("remotejobs") == [
        "https://remotejobs.org/api/v1/jobs?category=programming&limit=20&offset=0"
    ]


def test_split_items_chunks_listings_with_own_url() -> None:
    chunks = split_items(remotejobs_page(), "remotejobs")
    assert len(chunks) == 1
    assert chunks[0].url == "https://remotejobs.org/remote-jobs/acme-backend-engineer"
    assert "Backend Engineer at Acme Robotics" in chunks[0].text
    assert "distributed systems" in chunks[0].text


def test_split_items_skips_short_and_urlless_listings() -> None:
    chunks = split_items(remotejobs_page(), "remotejobs")
    urls = [chunk.url for chunk in chunks]
    assert "https://remotejobs.org/remote-jobs/ghar-gardener" not in urls  # too short
    assert all("No URL" not in chunk.text for chunk in chunks)


def test_next_links_follows_has_more_flag() -> None:
    page = remotejobs_page(remotejobs_response(offset=0, limit=20, has_more=True))
    assert next_links(page, "remotejobs") == [
        "https://remotejobs.org/api/v1/jobs?category=programming&limit=20&offset=20"
    ]


def test_next_links_empty_when_has_more_is_false() -> None:
    assert next_links(remotejobs_page(), "remotejobs") == []


def test_malformed_payload_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not a RemoteJobs.org"):
        split_items(remotejobs_page(json.dumps({"not": "expected"})), "remotejobs")
    with pytest.raises(ValueError):
        split_items(remotejobs_page("{{{ not json"), "remotejobs")
