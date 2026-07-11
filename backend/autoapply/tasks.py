"""Huey wiring for auto-apply (PHASE11.md step 6) — mirrors
`backend.scraper.tasks`' own shape exactly: the API route does the fast,
synchronous work (pre-flight checks, row creation) and enqueues a task for
the slow, real browser work, which runs on the Huey consumer thread, not
the request thread.
"""

from sqlalchemy.orm import Session

from backend.autoapply import executor, planner
from backend.db import repo
from backend.db.models import ApplicantProfile, Application, Company, Job
from backend.scraper.tasks import huey


@huey.task()  # type: ignore[untyped-decorator]  # huey ships no stubs
def plan_application_page_task(
    application_id: int, job_id: int, company_id: int, is_first_application: bool
) -> None:
    """Runs the real, slow browser work for an Application the API route
    already created (status "pending") after its own pre-flight checks
    passed synchronously."""
    engine = repo.make_engine()
    with Session(engine) as session:
        application = session.get(Application, application_id)
        job = session.get(Job, job_id)
        company = session.get(Company, company_id)
        if application is None or job is None or company is None:  # pragma: no cover
            return
        profile_row = session.get(ApplicantProfile, 1)
        if profile_row is None:  # pragma: no cover - checked synchronously before enqueue
            return
        planner.run_page_planning(
            session, application, job, company, profile_row, is_first_application
        )


@huey.task()  # type: ignore[untyped-decorator]  # huey ships no stubs
def execute_application_task(application_id: int) -> None:
    """Runs the confirmed-application executor for real — enqueued only
    after POST /applications/{id}/confirm records a real confirmation
    event; execute_submission itself still refuses to run without one."""
    engine = repo.make_engine()
    with Session(engine) as session:
        application = session.get(Application, application_id)
        if application is None:  # pragma: no cover
            return
        executor.execute_submission(session, application)
