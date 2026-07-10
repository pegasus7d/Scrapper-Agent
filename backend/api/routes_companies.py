"""Company discovery endpoints (PHASE7.md step 5) — split from routes.py to
stay under CLAUDE.md's 300-line file cap.
"""

import logging

from fastapi import APIRouter

from backend.api.deps import SessionDep
from backend.api.dto import CompanyList, CompanyOut, DiscoveryResult, ResolutionResult
from backend.db import repo
from backend.scraper.discovery import build_yc_fetcher, discover_yc_companies
from backend.scraper.resolve import resolve_unresolved_companies

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/companies")
def list_companies(session: SessionDep) -> CompanyList:
    companies = repo.list_companies(session)
    return CompanyList(
        items=[CompanyOut.model_validate(c) for c in companies], total=len(companies)
    )


@router.post("/companies/discover")
def discover_companies(session: SessionDep) -> DiscoveryResult:
    """Run one real discovery pass against the YC company directory,
    storing any real company names not already on file (step 5's own
    smoke test hits this endpoint directly)."""
    names = discover_yc_companies(build_yc_fetcher())
    discovered = sum(1 for name in names if repo.save_company(session, name))
    total = len(repo.list_companies(session))
    return DiscoveryResult(discovered=discovered, total=total)


@router.post("/companies/resolve")
def resolve_companies(session: SessionDep) -> ResolutionResult:
    """Probe every unresolved company against Greenhouse/Lever (step 6's
    own smoke test hits this endpoint directly)."""
    summary = resolve_unresolved_companies(session)
    return ResolutionResult(checked=summary.checked, resolved=summary.resolved)
