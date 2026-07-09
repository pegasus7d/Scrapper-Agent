"""Tests for the HN "Who is hiring?" jobs source."""

import json

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import Chunk, next_links, seed_urls, split_items

SEARCH_URL = seed_urls("hn")[0]

SEARCH_RESPONSE = json.dumps(
    {
        "hits": [
            {"title": "Ask HN: Who wants to be hired? (July 2026)", "objectID": "111"},
            {"title": "Ask HN: Who is hiring? (July 2026)", "objectID": "222"},
            {"title": "Ask HN: Who is hiring? (June 2026)", "objectID": "333"},
        ]
    }
)

LONG_TEXT = (
    "<p>Acme Robotics | Senior Backend Engineer | Remote | $160k</p>"
    "<p>We build warehouse robots. Python&amp;Go. Apply at "
    '<a href="https://acme.example">acme.example</a></p>'
)

THREAD_RESPONSE = json.dumps(
    {
        "id": 222,
        "children": [
            {"id": 1001, "text": LONG_TEXT},
            {"id": 1002, "text": None},
            {"id": 1003, "text": "<p>email me</p>"},
        ],
    }
)


def search_page(raw: str = SEARCH_RESPONSE) -> Page:
    return Page(url=SEARCH_URL, markdown="", raw=raw)


def thread_page(raw: str = THREAD_RESPONSE) -> Page:
    return Page(url="https://hn.algolia.com/api/v1/items/222", markdown="", raw=raw)


def test_seed_urls_hn_points_at_algolia_search() -> None:
    assert "hn.algolia.com" in SEARCH_URL
    assert "whoishiring" in SEARCH_URL


def test_next_links_picks_newest_hiring_thread_not_wants_to_be_hired() -> None:
    assert next_links(search_page(), "hn") == ["https://hn.algolia.com/api/v1/items/222"]


def test_search_page_recognized_after_url_normalization() -> None:
    # The pipeline normalizes URLs before fetching, which re-encodes the
    # query ("story,author..." -> "story%2Cauthor...") — detection must
    # not depend on the exact seed string.
    normalized = SEARCH_URL.replace("story,author", "story%2Cauthor")
    page = Page(url=normalized, markdown="", raw=SEARCH_RESPONSE)
    assert next_links(page, "hn") == ["https://hn.algolia.com/api/v1/items/222"]
    assert split_items(page, "hn") == []


def test_next_links_no_hiring_thread_raises() -> None:
    raw = json.dumps({"hits": [{"title": "Show HN: something", "objectID": "9"}]})
    with pytest.raises(ValueError, match="no 'Who is hiring"):
        next_links(search_page(raw), "hn")


def test_next_links_on_thread_page_is_empty() -> None:
    assert next_links(thread_page(), "hn") == []


def test_split_items_on_search_page_is_empty() -> None:
    assert split_items(search_page(), "hn") == []


def test_split_items_chunks_with_permalinks_and_clean_text() -> None:
    chunks = split_items(thread_page(), "hn")
    assert chunks == [
        Chunk(
            text=(
                "Acme Robotics | Senior Backend Engineer | Remote | $160k "
                "We build warehouse robots. Python&Go. Apply at acme.example"
            ),
            url="https://news.ycombinator.com/item?id=1001",
        )
    ]


def test_split_items_skips_deleted_and_tiny_comments() -> None:
    urls = [chunk.url for chunk in split_items(thread_page(), "hn")]
    assert "https://news.ycombinator.com/item?id=1002" not in urls  # deleted
    assert "https://news.ycombinator.com/item?id=1003" not in urls  # too short


def test_split_items_malformed_json_raises_value_error() -> None:
    with pytest.raises(ValueError):
        split_items(thread_page("{{{ not json"), "hn")
