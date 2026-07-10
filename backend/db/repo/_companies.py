"""Discovered-company CRUD (PHASE7.md step 5)."""

from datetime import UTC, datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from backend.db.models import Company


def mark_company_checked(
    session: Session,
    company: Company,
    *,
    slug: str | None = None,
    ats_provider: str | None = None,
    checked_at: datetime | None = None,
) -> None:
    """Record a slug-resolution attempt (PHASE7.md step 6). Always updates
    last_checked_at, whether or not a real ATS match was found — a resolved
    company simply also gets slug/ats_provider set."""
    company.slug = slug
    company.ats_provider = ats_provider
    company.last_checked_at = checked_at or datetime.now(UTC)
    session.commit()


def save_company(session: Session, name: str, *, batch: str | None = None) -> bool:
    """Insert one discovered company; returns False when already known.
    `batch` (PHASE8.md step 5) is only meaningful for YC-discovered
    companies — any other discovery source leaves it null."""
    exists = session.scalar(select(Company.id).where(Company.name == name))
    if exists is not None:
        return False
    session.add(Company(name=name, batch=batch, discovered_at=datetime.now(UTC)))
    session.commit()
    return True


def _company_query(*, ats_provider: str | None, q: str | None) -> Select[tuple[Company]]:
    query = select(Company).order_by(Company.id.desc())
    if ats_provider:
        query = query.where(Company.ats_provider == ats_provider)
    if q:
        query = query.where(Company.name.ilike(f"%{q}%"))
    return query


def list_companies(
    session: Session,
    *,
    ats_provider: str | None = None,
    q: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Company], int]:
    """One page of discovered companies (newest first) matching the
    filters, plus the total matching count (independent of limit/offset) —
    same shape as repo.list_jobs (PHASE8.md step 1). limit/offset default
    to "one big page" rather than requiring every internal caller (the
    discover/resolve endpoints just want a total; tests just want every
    row) to pass them explicitly."""
    query = _company_query(ats_provider=ats_provider, q=q)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.limit(limit).offset(offset)).all()
    return list(rows), total


def unresolved_companies(session: Session) -> list[Company]:
    """Companies with no known ATS provider yet — slug resolution's input (step 6)."""
    query = select(Company).where(Company.ats_provider.is_(None))
    return list(session.scalars(query.order_by(Company.id)).all())
