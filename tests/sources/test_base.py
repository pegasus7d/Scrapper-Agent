"""Tests for `clean_html()`'s script/style leak fix (PHASE14.md step 1)."""

from backend.scraper.sources._base import clean_html


def test_clean_html_strips_tags_and_entities() -> None:
    assert clean_html("<p>Hello &amp; welcome</p>") == "Hello & welcome"


def test_clean_html_collapses_whitespace() -> None:
    assert clean_html("<p>a</p>\n\n  <p>b</p>") == "a b"


def test_clean_html_drops_script_block_content() -> None:
    html_text = "<div>Job description</div><script>var x = analytics.track();</script>"
    result = clean_html(html_text)
    assert "analytics" not in result
    assert result == "Job description"


def test_clean_html_drops_style_block_content() -> None:
    html_text = "<style>.foo { color: red; }</style><div>Job description</div>"
    result = clean_html(html_text)
    assert "color" not in result
    assert result == "Job description"


def test_clean_html_drops_multiple_script_blocks() -> None:
    html_text = (
        "<script>window.a = 1;</script>"
        "<div>Real content here</div>"
        "<script src='x.js'>window.b = 2;</script>"
    )
    result = clean_html(html_text)
    assert "window" not in result
    assert result == "Real content here"


def test_clean_html_is_case_insensitive_for_script_and_style_tags() -> None:
    html_text = "<SCRIPT>var x = 1;</SCRIPT><div>content</div>"
    result = clean_html(html_text)
    assert "var x" not in result
    assert result == "content"


def test_clean_html_still_a_no_op_for_isolated_json_snippets() -> None:
    # Every existing source only ever runs clean_html() on a small JSON field
    # value with no <script>/<style> tags — confirm the fix doesn't change
    # that path's output.
    snippet = "We need a <b>Python</b> engineer with 5+ years experience."
    assert clean_html(snippet) == "We need a Python engineer with 5+ years experience."
