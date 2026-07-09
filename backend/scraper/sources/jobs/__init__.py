"""Job-board sources registry (PHASE4.md step 1)."""

from backend.scraper.sources._base import Source
from backend.scraper.sources.jobs.arbeitnow import Arbeitnow
from backend.scraper.sources.jobs.himalayas import Himalayas
from backend.scraper.sources.jobs.hn import HNJobs
from backend.scraper.sources.jobs.remotejobs import RemoteJobsOrg
from backend.scraper.sources.jobs.remoteok import RemoteOK
from backend.scraper.sources.jobs.weworkremotely import WeWorkRemotely

SOURCES: dict[str, Source] = {
    "hn": HNJobs(),
    "remoteok": RemoteOK(),
    "weworkremotely": WeWorkRemotely(),
    "arbeitnow": Arbeitnow(),
    "himalayas": Himalayas(),
    "remotejobs": RemoteJobsOrg(),
}
