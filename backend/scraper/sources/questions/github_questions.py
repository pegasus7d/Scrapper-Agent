"""Curated GitHub interview-question banks (PHASE3.md step 4).

Reddit, LeetCode Discuss, and Blind all turned out to be unscrapable
(DESIGN.md §3, PHASE3.md) — rather than find yet another forum, ingest permissively-licensed,
human-curated content instead. `h5bp/Front-end-Developer-Interview-Questions`
(MIT licensed, 60k+ stars) is a flat markdown bullet list of real questions,
no answers, no company attribution, served from `raw.githubusercontent.com`
(GitHub's CDN, no `robots.txt` at all — built for programmatic access, same
category as their REST API).

One markdown file = one page; each top-level bullet (plus its sub-bullets,
which are follow-ups on the same question) = one `Chunk`. `Chunk.url` points
at the GitHub *blob* view with a `#L{n}` line anchor — computed from the raw
file's own line numbers, since both views share the same underlying file.
"""

import logging
import re
from typing import Literal

from backend.scraper.fetcher import Page
from backend.scraper.sources._base import Chunk, collapse_whitespace

logger = logging.getLogger(__name__)

# These questions are pre-curated by maintainers, not noisy forum text — a
# short, concrete question ("Explain hoisting.") is still perfectly good
# content, so MIN_CHUNK_CHARS (calibrated for job postings/comments) would
# wrongly reject most of them. A small floor just catches empty bullets.
_MIN_QUESTION_CHARS = 10

_OWNER_REPO = "h5bp/Front-end-Developer-Interview-Questions"
_BRANCH = "main"
_FILES = ("javascript-questions.md", "css-questions.md", "html-questions.md")
_RAW_URL = f"https://raw.githubusercontent.com/{_OWNER_REPO}/{_BRANCH}/src/questions/{{file}}"
_BLOB_URL = f"https://github.com/{_OWNER_REPO}/blob/{_BRANCH}/src/questions/{{file}}#L{{line}}"

_BULLET = re.compile(r"^(\s*)\* (.*)")


class GitHubQuestions:
    """Curated markdown question banks → one Chunk per top-level bullet."""

    kind: Literal["jobs", "questions"] = "questions"

    def seed_urls(self) -> list[str]:
        return [_RAW_URL.format(file=name) for name in _FILES]

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
        chunks.append(Chunk(text=text, url=_BLOB_URL.format(file=filename, line=start_line)))

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
