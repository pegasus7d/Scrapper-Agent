"""Persistence layer, split by responsibility (DESIGN.md §2):

- `_writes`: run lifecycle, dedupe normalization, item saving.
- `_queries`: paginated lists, filters, export, dashboard stats.
- `_schedules`: schedule CRUD and the due-check the scheduler polls.
- `_companies`: discovered-company CRUD (PHASE7.md step 5).

Re-exported flat here so callers keep writing `repo.save_job(...)`,
`repo.list_jobs(...)`, `repo.due_schedules(...)` etc. — the split is purely
an internal file-size concern (CLAUDE.md's 300-line cap), not a public API
change.
"""

from ._companies import list_companies, mark_company_checked, save_company, unresolved_companies
from ._queries import (
    Stats,
    compute_stats,
    export_jobs,
    export_questions,
    get_run,
    list_jobs,
    list_questions,
    list_runs,
    set_job_starred,
    set_job_status,
)
from ._schedules import (
    create_schedule,
    due_schedules,
    list_schedules,
    mark_schedule_run,
    set_schedule_enabled,
)
from ._writes import (
    MAX_RUN_ERRORS,
    active_run_exists,
    cancel_requested,
    create_run,
    finish_run,
    item_url_exists,
    make_engine,
    normalize_url,
    question_hash,
    record_error,
    recover_stale_runs,
    request_cancel,
    save_job,
    save_question,
)

__all__ = [
    "MAX_RUN_ERRORS",
    "Stats",
    "active_run_exists",
    "cancel_requested",
    "compute_stats",
    "create_run",
    "create_schedule",
    "due_schedules",
    "export_jobs",
    "export_questions",
    "finish_run",
    "get_run",
    "item_url_exists",
    "list_companies",
    "list_jobs",
    "list_questions",
    "list_runs",
    "list_schedules",
    "make_engine",
    "mark_company_checked",
    "mark_schedule_run",
    "normalize_url",
    "question_hash",
    "record_error",
    "recover_stale_runs",
    "request_cancel",
    "save_company",
    "save_job",
    "save_question",
    "set_job_starred",
    "set_job_status",
    "set_schedule_enabled",
    "unresolved_companies",
]
