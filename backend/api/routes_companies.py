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
from backend.scraper.discovery import build_yc_fetcher, discover_yc_companies
from backend.scraper.resolve import resolve_unresolved_companies
from backend.scraper.tasks import run_scrape_task

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/companies")
def list_companies(
    session: SessionDep,
    ats_provider: str | None = None,
    q: str | None = None,
    limit: LimitParam = 20,
    offset: OffsetParam = 0,
) -> CompanyList:
    companies, total = repo.list_companies(
        session, ats_provider=ats_provider, q=q, limit=limit, offset=offset
    )
    return CompanyList(items=[CompanyOut.model_validate(c) for c in companies], total=total)


@router.post("/companies/discover")
def discover_companies(session: SessionDep) -> DiscoveryResult:
    """Run one real discovery pass against the YC company directory,
    storing any real company names not already on file (step 5's own
    smoke test hits this endpoint directly)."""
    names = discover_yc_companies(build_yc_fetcher())
    discovered = sum(1 for name in names if repo.save_company(session, name))
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
