"""Discovered-company CRUD (PHASE7.md step 5)."""

from datetime import UTC, datetime

from sqlalchemy import select
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


def save_company(session: Session, name: str) -> bool:
    """Insert one discovered company; returns False when already known."""
    exists = session.scalar(select(Company.id).where(Company.name == name))
    if exists is not None:
        return False
    session.add(Company(name=name, discovered_at=datetime.now(UTC)))
    session.commit()
    return True


def list_companies(session: Session) -> list[Company]:
    """Every discovered company, newest first."""
    return list(session.scalars(select(Company).order_by(Company.id.desc())).all())


def unresolved_companies(session: Session) -> list[Company]:
    """Companies with no known ATS provider yet — slug resolution's input (step 6)."""
    query = select(Company).where(Company.ats_provider.is_(None))
    return list(session.scalars(query.order_by(Company.id)).all())
