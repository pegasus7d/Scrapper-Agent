"""Company discovery/resolution/scrape endpoints (PHASE7.md steps 5-7) —
split from routes.py to stay under CLAUDE.md's 300-line file cap.
"""

import logging

from fastapi import APIRouter, HTTPException

from backend.api.deps import LimitParam, OffsetParam, SessionDep
from backend.api.dto import CompanyList, CompanyOut, DiscoveryResult, ResolutionResult, RunCreated
from backend.db import repo
from backend.db.models import Company
from backend.scraper import sources
from backend.scraper.discovery import DISCOVERY_SOURCES, discover_and_save_companies
from backend.scraper.resolve import resolve_unresolved_companies
from backend.scraper.tasks import run_scrape_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/companies")
def list_companies(
    session: SessionDep,
    ats_provider: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> CompanyList:
    companies, total = repo.list_companies(
        session, ats_provider=ats_provider, source=source, q=q, limit=limit, offset=offset
    )
    return CompanyList(items=[CompanyOut.model_validate(c) for c in companies], total=total)


@router.post("/companies/discover")
def discover_companies(session: SessionDep, source: str = "yc") -> DiscoveryResult:
    """Run one real discovery pass against the chosen source — "yc" (a real
    scrolled session, PHASE8.md step 5 — not just the first 40 cards),
    "largest_us_companies" (PHASE8.md step 6, Wikipedia's revenue-ranked
    table), "a16z" (PHASE8.md step 9, its full portfolio inline on one
    page), or "sequoia" (PHASE8.md step 9, a real tab-open + "Load More"
    click sequence) — storing any real companies not already on file.
    Defaults to "yc" for backward compatibility with the original
    single-source endpoint."""
    if source not in DISCOVERY_SOURCES:
        raise HTTPException(422, f"unknown discovery source: {source}")
    discovered = discover_and_save_companies(session, source)
    _, total = repo.list_companies(session)
    return DiscoveryResult(discovered=discovered, total=total)


@router.post("/companies/resolve")
def resolve_companies(session: SessionDep) -> ResolutionResult:
    """Probe every unresolved company against Greenhouse/Lever (step 6's
    own smoke test hits this endpoint directly)."""
    summary = resolve_unresolved_companies(session)
    return ResolutionResult(checked=summary.checked, resolved=summary.resolved)


@router.post("/companies/{company_id}/scrape", status_code=201)
def scrape_company(company_id: int, session: SessionDep) -> RunCreated:
    """Run a real scrape against one resolved company (step 7's own smoke
    test hits this endpoint directly) — registers its Source dynamically
    (sources.register_company_source) and enqueues it the same way
    POST /runs does."""
    company = session.get(Company, company_id)
    if company is None:
        raise HTTPException(404, "company not found")
    if company.ats_provider is None:
        raise HTTPException(422, "company has not been resolved to an ATS provider yet")
    if repo.active_run_exists(session):
        raise HTTPException(409, "a run is already active")
    key = sources.register_company_source(company)
    run = repo.create_run(session, "jobs", key)
    run_scrape_task(run.id)
    return RunCreated(run_id=run.id)
