"""Safety-control infrastructure for auto-apply (PHASE10.md step 3) —
infrastructure only, no real ATS interaction yet. A real application
submission stays gated behind its own separate checkpoint per
PHASE10.md's "submission gate" section, regardless of how these controls
are exercised.

Real prior-art adopted here (PHASE10.md's own research, cited in full
there): OpenHands' fail-safe-to-HIGH SecurityRisk classification, its
pluggable ConfirmationPolicy, and its StuckDetector repetition guard.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend import config
from backend.db.models import Application, AutoApplySettings, Company

_SETTINGS_ROW_ID = 1


class KillSwitchActive(Exception):
    """Raised when an auto-apply action is attempted while the kill switch is on."""


class ApplicationCapReached(Exception):
    """Raised when MAX_APPLICATIONS_PER_DAY would be exceeded."""


class PacingViolation(Exception):
    """Raised when MIN_SECONDS_BETWEEN_APPLICATIONS hasn't elapsed since the
    last application attempt."""


def _settings(session: Session) -> AutoApplySettings:
    row = session.get(AutoApplySettings, _SETTINGS_ROW_ID)
    if row is None:
        row = AutoApplySettings(id=_SETTINGS_ROW_ID, kill_switch_enabled=False)
        session.add(row)
        session.commit()
    return row


def kill_switch_enabled(session: Session) -> bool:
    """Whether the single, toggleable kill switch is currently on."""
    return _settings(session).kill_switch_enabled


def set_kill_switch(session: Session, enabled: bool) -> None:
    """Flip the kill switch — a real DB row, not a config.py constant, so it
    can be toggled without a restart."""
    row = _settings(session)
    row.kill_switch_enabled = enabled
    session.commit()


def classify_risk(*, is_first_application_to_company: bool, llm_confidence: float | None) -> str:
    """Returns "low" or "high", failing safe to "high" on any ambiguity —
    never silently "low" (mirrors OpenHands' fail-safe-to-HIGH SecurityRisk
    design). A first application to a company is inherently unproven; a
    missing or low-confidence LLM read on the form is inherently uncertain.
    """
    if is_first_application_to_company:
        return "high"
    if llm_confidence is None or llm_confidence < config.AUTOAPPLY_LLM_CONFIDENCE_THRESHOLD:
        return "high"
    return "low"


def requires_confirmation(risk_level: str) -> bool:
    """Whether SUBMIT_CONFIRMATION_POLICY (config.py) pauses this risk level
    for a human to confirm before a real submission."""
    if config.SUBMIT_CONFIRMATION_POLICY == "always":
        return True
    if config.SUBMIT_CONFIRMATION_POLICY == "never":
        return False
    return risk_level == "high"


def is_company_blocked(company: Company) -> bool:
    """Per-company opt-out (Company.auto_apply_blocked), checked before any
    application attempt starts."""
    return company.auto_apply_blocked


def has_existing_application(session: Session, *, company_id: int, job_id: int | None) -> bool:
    """True when an Application row already exists for this company/job
    pair — the dedup check, preventing a duplicate real submission."""
    query = select(Application.id).where(Application.company_id == company_id)
    query = query.where(Application.job_id == job_id) if job_id is not None else query
    return session.scalar(query) is not None


def active_application_exists(session: Session) -> bool:
    """True while any application is mid-planning ("pending" — the real
    browser work hasn't reached awaiting_confirmation/failed yet). Mirrors
    active_run_exists' own "running" check (PHASE9.md); a real, global
    one-at-a-time rule, same as scrape runs. Rows already sitting at
    awaiting_confirmation don't count — several can be reviewed at once,
    only concurrent *planning* is disallowed."""
    return session.scalar(select(Application.id).where(Application.status == "pending")) is not None


def applications_started_today(session: Session) -> int:
    """Count of Application rows started since midnight UTC."""
    since = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    query = select(func.count()).select_from(Application).where(Application.started_at >= since)
    return session.scalar(query) or 0


def check_daily_cap(session: Session) -> None:
    """Raise ApplicationCapReached once MAX_APPLICATIONS_PER_DAY would be exceeded."""
    if applications_started_today(session) >= config.MAX_APPLICATIONS_PER_DAY:
        raise ApplicationCapReached(
            f"already started {config.MAX_APPLICATIONS_PER_DAY} applications today"
        )


def seconds_since_last_application(session: Session) -> float | None:
    """Real elapsed time since the most recently started Application, or
    None when no application has ever been attempted."""
    last_started_at = session.scalar(select(func.max(Application.started_at)))
    if last_started_at is None:
        return None
    if last_started_at.tzinfo is None:
        last_started_at = last_started_at.replace(tzinfo=UTC)
    return (datetime.now(UTC) - last_started_at).total_seconds()


def check_pacing(session: Session) -> None:
    """Raise PacingViolation when the last application started less than
    MIN_SECONDS_BETWEEN_APPLICATIONS ago — a human applying one at a time
    doesn't fire submissions back-to-back."""
    elapsed = seconds_since_last_application(session)
    if elapsed is not None and elapsed < config.MIN_SECONDS_BETWEEN_APPLICATIONS:
        raise PacingViolation(
            f"only {elapsed:.0f}s since the last application "
            f"(minimum {config.MIN_SECONDS_BETWEEN_APPLICATIONS}s)"
        )


@dataclass
class StuckDetector:
    """OpenHands' repetition/loop-detection pattern, applied at the
    per-application-attempt level: stop after too many consecutive failed
    actions rather than retrying indefinitely against a form that isn't
    responding the way the filler expects."""

    max_consecutive_failures: int = field(
        default_factory=lambda: config.MAX_CONSECUTIVE_APPLICATION_FAILURES
    )
    _consecutive_failures: int = field(default=0, init=False)

    def record(self, *, success: bool) -> None:
        self._consecutive_failures = 0 if success else self._consecutive_failures + 1

    @property
    def stuck(self) -> bool:
        return self._consecutive_failures >= self.max_consecutive_failures
