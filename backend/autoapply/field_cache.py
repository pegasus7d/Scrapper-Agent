"""Cached Greenhouse/Lever field detection (PHASE12.md step 2): Playwright's
live `detect_fields` DOM query + accessibility-tree cross-reference is
skipped on a cache hit, replaced by a much cheaper "does each cached
selector still resolve on this live page" check — the OpenCLI-inspired
"record once, replay" pattern applied without adopting OpenCLI itself
(CLAUDE.md: no new dependencies without a stated reason).

Keyed by (ats_provider, company_id), not a hash of detect_fields' own
output — a form's shape can only be known *after* running detection, so a
fingerprint of that output can never be looked up *before* running it (a
real design correction from PHASE12.md's original "form_fingerprint" draft,
see this step's own "Done." writeup). Greenhouse/Lever forms are
configured at a company's ATS account level, so every posting from the
same company on the same ATS shares one real form shape in practice; a
cache hit is still verified live, never trusted blindly, since a company
can add or remove a custom question at any time.
"""

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Any

from playwright.sync_api import Page
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.autoapply.filler_types import DetectedField
from backend.db.models import FieldDetectionCache


def _to_field(data: dict[str, Any]) -> DetectedField:
    return DetectedField(**data)


def get_cached_fields(
    session: Session, ats_provider: str, company_id: int
) -> list[DetectedField] | None:
    """The cached field map for this company's ATS form, if one exists."""
    row = session.scalar(
        select(FieldDetectionCache).where(
            FieldDetectionCache.ats_provider == ats_provider,
            FieldDetectionCache.company_id == company_id,
        )
    )
    if row is None:
        return None
    return [_to_field(f) for f in row.field_map]


def save_cached_fields(
    session: Session, ats_provider: str, company_id: int, fields: list[DetectedField]
) -> None:
    """Overwrite this company's cached field map with a freshly-detected
    one — called after every live detection, whether that live detection
    ran because of a cache miss or because a cache hit's selectors failed
    to resolve. A stale cache row must never survive past this call."""
    row = session.scalar(
        select(FieldDetectionCache).where(FieldDetectionCache.company_id == company_id)
    )
    field_map = [asdict(field) for field in fields]
    if row is None:
        row = FieldDetectionCache(
            ats_provider=ats_provider,
            company_id=company_id,
            field_map=field_map,
            cached_at=datetime.now(UTC),
        )
        session.add(row)
    else:
        row.ats_provider = ats_provider
        row.field_map = field_map
        row.cached_at = datetime.now(UTC)
    session.commit()


def fields_resolve_on_page(page: Page, fields: list[DetectedField]) -> bool:
    """True only if every cached selector still matches at least one real
    element on the live page — a company can add or remove a custom
    question at any time, so a cache hit is never trusted without this
    check."""
    return all(page.locator(field.selector).count() > 0 for field in fields)
