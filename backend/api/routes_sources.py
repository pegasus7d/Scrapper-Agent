"""Source health endpoint (PHASE12.md step 1) — split from routes.py per
CLAUDE.md's 300-line cap, same pattern as routes_companies.py.
"""

from fastapi import APIRouter

from backend.api.dto import SourceHealthOut
from backend.scraper.health import check_all_sources

router = APIRouter()


@router.get("/sources/health")
def sources_health() -> list[SourceHealthOut]:
    """Real liveness check across every registered source — one cheap
    request each, no LLM call, no full scrape (backend/scraper/health.py).
    """
    return [
        SourceHealthOut(name=r.name, kind=r.kind, status=r.status, detail=r.detail)
        for r in check_all_sources()
    ]
