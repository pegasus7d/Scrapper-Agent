"""Tests for the RemoteOK source."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

LONG_DESCRIPTION = (
    "We build developer tools for distributed systems. You will design APIs, "
    "review pull requests, and mentor junior engineers on a small remote team."
)

REMOTEOK_RESPONSE = json.dumps(
    [
        {"last_updated": 123, "legal": "please link back to RemoteOK"},
        {
            "id": "1",
            "position": "Backend Engineer",
            "company": "Acme Robotics",
            "location": "Remote",
            "salary_min": 90000,
            "salary_max": 130000,
            "description": f"<p>{LONG_DESCRIPTION}</p>",
            "url": "https://remoteok.com/remote-jobs/1",
            "apply_url": "https://remoteok.com/remote-jobs/1",
        },
        {"id": "2", "position": "Gardener", "company": "Ghar", "url": "https://remoteok.com/2"},
        {"id": "3", "position": "No URL Role", "company": "X", "description": LONG_DESCRIPTION},
    ]
)


def remoteok_page(raw: str = REMOTEOK_RESPONSE) -> Page:
    return Page(url=seed_urls("remoteok")[0], markdown="", raw=raw)


def test_remoteok_seed_url_is_the_public_api() -> None:
    assert seed_urls("remoteok") == ["https://remoteok.com/api"]


def test_remoteok_split_items_chunks_listings_with_own_url() -> None:
    chunks = split_items(remoteok_page(), "remoteok")
    assert len(chunks) == 1
    assert chunks[0].url == "https://remoteok.com/remote-jobs/1"
    assert "Backend Engineer at Acme Robotics" in chunks[0].text
    assert "distributed systems" in chunks[0].text


def test_remoteok_split_items_skips_legal_notice_short_and_urlless_listings() -> None:
    urls = [chunk.url for chunk in split_items(remoteok_page(), "remoteok")]
    assert "https://remoteok.com/2" not in urls  # too short (no description)
    assert all("No URL" not in chunk.text for chunk in split_items(remoteok_page(), "remoteok"))


def test_remoteok_next_links_is_empty() -> None:
    assert next_links(remoteok_page(), "remoteok") == []


def test_remoteok_malformed_payload_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not a RemoteOK"):
        split_items(remoteok_page(json.dumps({"not": "a list"})), "remoteok")
    with pytest.raises(ValueError):
        split_items(remoteok_page("{{{ not json"), "remoteok")
