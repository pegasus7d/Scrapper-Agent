"""Tests for the curated FAQGURU question-bank source (PHASE5.md step 7)."""

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

# Mirrors FAQGURU's real structure: a table-of-contents of markdown links
# (no `###` prefix) followed by the real content as `### Question` headings,
# each with a prose/code-block answer the parser deliberately discards (see
# github_questions.py's module docstring for why — a real local-model smoke
# test showed keeping the answer text tanks extraction reliability).
SAMPLE_MD = """## JavaScript

[What is Coercion in JavaScript?](#what-is-coercion-in-javascript)

[What is typeof operator?](#what-is-typeof-operator)



### What is Coercion in JavaScript?

In JavaScript conversion between two built-in types is called coercion.

[[↑] Back to top](#JavaScript)
### What is typeof operator?

The typeof operator returns a string indicating the type of the operand.

[[↑] Back to top](#JavaScript)
### Ok
"""


def js_page(raw: str = SAMPLE_MD) -> Page:
    urls = seed_urls("faqguru-questions")
    js_url = next(u for u in urls if u.endswith("javascript.md"))
    return Page(url=js_url, markdown="", raw=raw)


def test_seed_urls_point_at_raw_githubusercontent() -> None:
    urls = seed_urls("faqguru-questions")
    assert len(urls) >= 1
    assert all("raw.githubusercontent.com/FAQGURU/FAQGURU" in url for url in urls)
    assert all(url.endswith(".md") for url in urls)


def test_split_items_ignores_the_table_of_contents_preamble() -> None:
    chunks = split_items(js_page(), "faqguru-questions")
    texts = [c.text for c in chunks]
    # The TOC's bracketed links never produced their own (bogus) chunks.
    assert not any(text.startswith("[") for text in texts)


def test_split_items_is_the_bare_question_only() -> None:
    chunks = split_items(js_page(), "faqguru-questions")
    coercion = next(c for c in chunks if "Coercion" in c.text)
    assert coercion.text == "What is Coercion in JavaScript?"
    # The answer body never made it into the chunk text.
    assert "built-in types" not in coercion.text
    assert "typeof operator" not in coercion.text  # didn't bleed into the next heading


def test_split_items_skips_tiny_headings() -> None:
    chunks = split_items(js_page(), "faqguru-questions")
    assert all(chunk.text != "Ok" for chunk in chunks)


def test_split_items_url_is_a_github_blob_line_anchor() -> None:
    chunks = split_items(js_page(), "faqguru-questions")
    first = next(c for c in chunks if "Coercion" in c.text)
    assert first.url.startswith("https://github.com/FAQGURU/FAQGURU/blob/master/")
    assert "topics/en/javascript.md#L" in first.url


def test_next_links_is_empty() -> None:
    assert next_links(js_page(), "faqguru-questions") == []


def test_split_items_no_headings_is_empty_list() -> None:
    assert split_items(js_page("## JavaScript\n\n[a link](#x)\n"), "faqguru-questions") == []
