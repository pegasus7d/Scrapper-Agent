"""Shared types and utilities for every source (DESIGN.md §10 step 1).

Kept separate from `__init__.py` so platform modules can import `Chunk` and
these helpers without a circular import back through the registry.
"""

import html
import re
from dataclasses import dataclass

# Skip one-liners ("email me!") that cannot possibly hold a job posting.
MIN_CHUNK_CHARS = 80

_TAGS = re.compile(r"<[^>]+>")
_WHITESPACE = re.compile(r"\s+")


@dataclass
class Chunk:
    text: str  # one item's cleaned text
    url: str  # that item's permalink — becomes posting_url / source_url


def clean_html(text: str) -> str:
    """Strip tags and entities from HTML, collapsing whitespace."""
    return _WHITESPACE.sub(" ", html.unescape(_TAGS.sub(" ", text))).strip()


def collapse_whitespace(text: str) -> str:
    """Collapse whitespace runs in already-plain text (no tags to strip)."""
    return _WHITESPACE.sub(" ", text).strip()
