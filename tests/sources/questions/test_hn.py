"""Tests for the HN interview-question search source."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

QUESTION_TEXT = (
    "<p>Amazon SDE2 onsite &amp; phone screen: they asked me to design a rate "
    "limiter, then two graph problems. Behavioral round was all LP stories.</p>"
)

INTERVIEWS_RESPONSE = json.dumps(
    {
        "hits": [
            {"objectID": "501", "comment_text": QUESTION_TEXT},
            {"objectID": "502", "comment_text": "<p>lol same</p>"},
            {"objectID": "503", "comment_text": None},
        ]
    }
)


def interviews_page(raw: str = INTERVIEWS_RESPONSE) -> Page:
    return Page(url=seed_urls("hn-interviews")[0], markdown="", raw=raw)


def test_interviews_seed_url_searches_comments() -> None:
    urls = seed_urls("hn-interviews")
    assert len(urls) == 1
    assert "hn.algolia.com" in urls[0]
    assert "tags=comment" in urls[0]


def test_interviews_split_items_chunks_comments_with_permalinks() -> None:
    chunks = split_items(interviews_page(), "hn-interviews")
    assert len(chunks) == 1
    assert chunks[0].text.startswith("Amazon SDE2 onsite & phone screen")
    assert chunks[0].url == "https://news.ycombinator.com/item?id=501"


def test_interviews_split_items_skips_short_and_empty_comments() -> None:
    urls = [chunk.url for chunk in split_items(interviews_page(), "hn-interviews")]
    assert "https://news.ycombinator.com/item?id=502" not in urls  # too short
    assert "https://news.ycombinator.com/item?id=503" not in urls  # no text


def test_interviews_next_links_is_empty() -> None:
    assert next_links(interviews_page(), "hn-interviews") == []


def test_interviews_malformed_payload_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not an Algolia comment-search"):
        split_items(interviews_page(json.dumps({"nope": 1})), "hn-interviews")
    with pytest.raises(ValueError):
        split_items(interviews_page("{{{ not json"), "hn-interviews")
