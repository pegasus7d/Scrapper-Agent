"""Tests for the curated GitHub question-bank source."""

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

SAMPLE_MD = """---
title: JavaScript Questions
---

* Explain event delegation.
* Explain how `this` works in JavaScript.
  * Can you give an example of one of the ways that working with `this` has changed in ES6?
* Ok
"""


def js_page(raw: str = SAMPLE_MD) -> Page:
    urls = seed_urls("github-questions")
    js_url = next(u for u in urls if u.endswith("javascript-questions.md"))
    return Page(url=js_url, markdown="", raw=raw)


def test_seed_urls_point_at_raw_githubusercontent() -> None:
    urls = seed_urls("github-questions")
    assert len(urls) >= 1
    assert all("raw.githubusercontent.com" in url for url in urls)
    assert all(url.endswith(".md") for url in urls)


def test_split_items_groups_sub_bullets_with_their_parent() -> None:
    chunks = split_items(js_page(), "github-questions")
    texts = [c.text for c in chunks]
    assert "Explain event delegation." in texts
    combined = next(t for t in texts if "this" in t)
    assert "Can you give an example" in combined  # sub-bullet folded into parent


def test_split_items_skips_tiny_bullets() -> None:
    chunks = split_items(js_page(), "github-questions")
    assert all(chunk.text != "Ok" for chunk in chunks)


def test_split_items_url_is_a_github_blob_line_anchor() -> None:
    chunks = split_items(js_page(), "github-questions")
    first = next(c for c in chunks if c.text == "Explain event delegation.")
    assert first.url.startswith("https://github.com/h5bp/")
    assert "/blob/main/src/questions/javascript-questions.md#L" in first.url


def test_next_links_is_empty() -> None:
    assert next_links(js_page(), "github-questions") == []


def test_split_items_empty_file_is_empty_list() -> None:
    assert split_items(js_page("---\ntitle: x\n---\n"), "github-questions") == []
