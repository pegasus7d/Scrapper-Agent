"""Discovered-company CRUD (PHASE7.md step 5)."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Company


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
