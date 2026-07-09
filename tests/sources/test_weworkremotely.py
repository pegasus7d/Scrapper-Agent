"""Tests for the WeWorkRemotely RSS source."""

import pytest

from backend.scraper.fetcher import Page
from backend.scraper.sources import next_links, seed_urls, split_items

LONG_DESCRIPTION = (
    "We build developer tools for distributed systems. You will design APIs, "
    "review pull requests, and mentor junior engineers on a small remote team."
)

RSS_RESPONSE = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>We Work Remotely</title>
    <item>
      <title>Acme Robotics: Senior Backend Engineer</title>
      <region>Anywhere in the World</region>
      <category>Back-End Programming</category>
      <description>&lt;p&gt;{LONG_DESCRIPTION}&lt;/p&gt;</description>
      <pubDate>Thu, 18 Jun 2026 02:18:33 +0000</pubDate>
      <guid>https://weworkremotely.com/remote-jobs/acme-senior-backend</guid>
      <link>https://weworkremotely.com/remote-jobs/acme-senior-backend</link>
    </item>
    <item>
      <title>Ghar: Gardener</title>
      <region>Anywhere</region>
      <category>All Other Remote Jobs</category>
      <description>&lt;p&gt;Short.&lt;/p&gt;</description>
      <guid>https://weworkremotely.com/remote-jobs/ghar-gardener</guid>
      <link>https://weworkremotely.com/remote-jobs/ghar-gardener</link>
    </item>
    <item>
      <title>No Link Co: Missing Link</title>
      <category>Front-End Programming</category>
      <description>&lt;p&gt;{LONG_DESCRIPTION}&lt;/p&gt;</description>
      <guid>https://weworkremotely.com/remote-jobs/no-link</guid>
    </item>
  </channel>
</rss>
"""


def rss_page(raw: str = RSS_RESPONSE) -> Page:
    return Page(url=seed_urls("weworkremotely")[0], markdown="", raw=raw)


def test_seed_url_is_the_programming_jobs_feed() -> None:
    urls = seed_urls("weworkremotely")
    assert len(urls) == 1
    assert urls[0].endswith(".rss")
    assert "weworkremotely.com" in urls[0]


def test_split_items_chunks_entries_with_own_link() -> None:
    chunks = split_items(rss_page(), "weworkremotely")
    assert len(chunks) == 1
    assert chunks[0].url == "https://weworkremotely.com/remote-jobs/acme-senior-backend"
    assert "Acme Robotics: Senior Backend Engineer" in chunks[0].text
    assert "Back-End Programming" in chunks[0].text
    assert "distributed systems" in chunks[0].text


def test_split_items_skips_short_and_linkless_entries() -> None:
    urls = [chunk.url for chunk in split_items(rss_page(), "weworkremotely")]
    assert "https://weworkremotely.com/remote-jobs/ghar-gardener" not in urls  # too short
    assert "https://weworkremotely.com/remote-jobs/no-link" not in urls  # no <link>


def test_next_links_is_empty() -> None:
    assert next_links(rss_page(), "weworkremotely") == []


def test_malformed_xml_raises_value_error() -> None:
    with pytest.raises(ValueError, match="not a valid RSS feed"):
        split_items(rss_page("not xml at all <<<"), "weworkremotely")
