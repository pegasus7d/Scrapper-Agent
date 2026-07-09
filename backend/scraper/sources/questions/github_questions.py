"""Curated GitHub interview-question banks (PHASE3.md step 4, PHASE5.md step 7).

Reddit, LeetCode Discuss, and Blind all turned out to be unscrapable
(DESIGN.md §3, PHASE3.md) — rather than find yet another forum, ingest permissively-licensed,
human-curated content instead, served from `raw.githubusercontent.com` (GitHub's
CDN, no `robots.txt` at all — built for programmatic access, same category as
their REST API). Two sources, two different file structures, verified for real
before writing their parsers rather than assumed:

- `h5bp/Front-end-Developer-Interview-Questions` (MIT, 60k+ stars) is a flat
  markdown bullet list — no answers, no company attribution.
- `FAQGURU/FAQGURU` (MIT, 5.1k stars) is structured completely differently:
  each file opens with a table of contents (`[question](#anchor)` links), then
  the real content as `### Question` headings followed by prose/code-block
  answers — confirmed by fetching a real file, not assumed from the README's
  "questions along with answers" description. Reusing the bullet parser for
  it would silently produce zero chunks (no `* ` lines below the TOC), so it
  gets its own heading-based grouping instead — and only the heading text
  becomes `Chunk.text`, discarding the answer body: `QuestionExtract` has no
  field for an answer, and a real local-model smoke test showed keeping the
  full question+answer text tanks extraction reliability (1/15 chunks
  extracted) versus the bare question alone (5/5).

Both: one markdown file = one page; `Chunk.url` points at the GitHub *blob*
view with a `#L{n}` line anchor — computed from the raw file's own line
numbers, since both views share the same underlying file.
"""

import logging
import re
from typing import Literal

from backend import config
from backend.scraper.fetcher import Page
from backend.scraper.sources._base import Chunk, collapse_whitespace

logger = logging.getLogger(__name__)

# These questions are pre-curated by maintainers, not noisy forum text — a
# short, concrete question ("Explain hoisting.") is still perfectly good
# content, so MIN_CHUNK_CHARS (calibrated for job postings/comments) would
# wrongly reject most of them. A small floor just catches empty bullets.
_MIN_QUESTION_CHARS = 10

_H5BP_OWNER_REPO = "h5bp/Front-end-Developer-Interview-Questions"
_H5BP_BRANCH = "main"
_H5BP_FILES = ("javascript-questions.md", "css-questions.md", "html-questions.md")
_H5BP_RAW_URL = (
    f"https://raw.githubusercontent.com/{_H5BP_OWNER_REPO}/{_H5BP_BRANCH}/src/questions/{{file}}"
)
_H5BP_BLOB_URL = (
    f"https://github.com/{_H5BP_OWNER_REPO}/blob/{_H5BP_BRANCH}/src/questions/{{file}}#L{{line}}"
)

_BULLET = re.compile(r"^(\s*)\* (.*)")


class GitHubQuestions:
    """h5bp's curated markdown question bank → one Chunk per top-level bullet."""

    kind: Literal["jobs", "questions"] = "questions"
    transport: Literal["httpx", "scrapling"] = "httpx"
    # GitHub's raw CDN has no robots.txt and is built for programmatic access —
    # it can take more load than a small job board, so skip the global delay.
    delay_s: float = config.REQUEST_DELAY_S / 4

    def seed_urls(self) -> list[str]:
        return [_H5BP_RAW_URL.format(file=name) for name in _H5BP_FILES]

    def next_links(self, page: Page) -> list[str]:
        return []  # each file is a complete, independent page

    def split_items(self, page: Page) -> list[Chunk]:
        return _bullet_chunks(page.raw, page.url)


def _bullet_chunks(raw: str, raw_url: str) -> list[Chunk]:
    """Group each top-level bullet with its sub-bullets into one Chunk."""
    filename = raw_url.rsplit("/", 1)[-1]
    groups = _group_bullets_by_top_level(raw)

    chunks: list[Chunk] = []
    skipped = 0
    for start_line, lines in groups:
        text = collapse_whitespace(" ".join(lines))
        if len(text) < _MIN_QUESTION_CHARS:
            skipped += 1
            continue
        chunks.append(Chunk(text=text, url=_H5BP_BLOB_URL.format(file=filename, line=start_line)))

    logger.info("github(%s): %d chunks, %d skipped", filename, len(chunks), skipped)
    return chunks


def _group_bullets_by_top_level(raw: str) -> list[tuple[int, list[str]]]:
    """Collect (start_line, [bullet texts]) — one group per top-level bullet,
    with its indented sub-bullets (follow-up questions on the same topic)."""
    groups: list[tuple[int, list[str]]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        match = _BULLET.match(line)
        if match is None:
            continue
        indent, content = match.group(1), match.group(2).strip()
        if not indent or not groups:
            groups.append((line_number, []))
        if content:
            groups[-1][1].append(content)
    return groups


_FAQGURU_OWNER_REPO = "FAQGURU/FAQGURU"
_FAQGURU_BRANCH = "master"
_FAQGURU_FILES = ("topics/en/javascript.md", "topics/en/react.md", "topics/en/nodejs.md")
_FAQGURU_RAW_PREFIX = f"https://raw.githubusercontent.com/{_FAQGURU_OWNER_REPO}/{_FAQGURU_BRANCH}/"
_FAQGURU_RAW_URL = _FAQGURU_RAW_PREFIX + "{file}"
_FAQGURU_BLOB_URL = (
    f"https://github.com/{_FAQGURU_OWNER_REPO}/blob/{_FAQGURU_BRANCH}/{{file}}#L{{line}}"
)

_HEADING = re.compile(r"^### (.*)")


class FaqguruQuestions:
    """FAQGURU's curated Q&A markdown → one Chunk per `### Question` heading
    (bare question text only — see module docstring for why the answer body
    is deliberately discarded)."""

    kind: Literal["jobs", "questions"] = "questions"
    transport: Literal["httpx", "scrapling"] = "httpx"
    delay_s: float = config.REQUEST_DELAY_S / 4

    def seed_urls(self) -> list[str]:
        return [_FAQGURU_RAW_URL.format(file=name) for name in _FAQGURU_FILES]

    def next_links(self, page: Page) -> list[str]:
        return []  # each file is a complete, independent page

    def split_items(self, page: Page) -> list[Chunk]:
        return _heading_chunks(page.raw, page.url)


def _heading_chunks(raw: str, raw_url: str) -> list[Chunk]:
    """Turn each `### Question` heading into one Chunk of just the question
    text — the table-of-contents preamble is skipped for free, since its
    `[text](#anchor)` lines never start with `###`."""
    filename = raw_url.removeprefix(_FAQGURU_RAW_PREFIX)
    chunks: list[Chunk] = []
    skipped = 0
    for line_number, line in enumerate(raw.splitlines(), start=1):
        match = _HEADING.match(line)
        if match is None:
            continue
        text = collapse_whitespace(match.group(1))
        if len(text) < _MIN_QUESTION_CHARS:
            skipped += 1
            continue
        chunks.append(
            Chunk(text=text, url=_FAQGURU_BLOB_URL.format(file=filename, line=line_number))
        )

    logger.info("faqguru(%s): %d chunks, %d skipped", filename, len(chunks), skipped)
    return chunks
