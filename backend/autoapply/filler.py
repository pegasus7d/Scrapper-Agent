"""Playwright-driven form fill-and-submit routine (PHASE10.md step 1) —
proves the automation mechanism against a form this project fully
controls (`test_form_server.py`), before ever pointing it at a real ATS.

Real design decisions (see PHASE10.md step 1's own write-up for the
prior-art research behind each):
(a) field detection uses a DOM query cross-referenced against a real
    accessibility-tree snapshot (browser-use's hybrid grounding, not
    vision/screenshot-only) — `Locator.aria_snapshot()`, not
    `page.accessibility.snapshot()`, which does not exist in the
    installed Playwright version (1.61.0; confirmed directly, a real,
    caught API mismatch, not assumed from older docs/tutorials);
(b) every action returns a structured ActionResult(success, error)
    instead of raising, with a consecutive-failure cap (browser-use);
(c) completion is an explicit, asserted done(success, reason) contract,
    verified against real confirmation-page state, never inferred;
(d) actions are discrete and typed (detect_fields, fill_field,
    upload_file, submit), not one opaque call (OpenHands).

Split across three modules to stay under CLAUDE.md's 300-line cap:
`filler_types.py` (dataclasses + label resolution), `filler_actions.py`
(fill_field/upload_file/submit), and this file (detection +
orchestration) — `ActionResult`/`DetectedField`/`DoneResult`/
`DetectAndFillResult` are re-exported here so existing callers keep
writing `filler.DetectedField` etc.
"""

import logging
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from backend.autoapply.filler_actions import fill_field, submit, upload_file
from backend.autoapply.filler_types import (
    ActionResult,
    DetectAndFillResult,
    DetectedField,
    DoneResult,
    resolve_label,
)

__all__ = [
    "ActionResult",
    "DetectAndFillResult",
    "DetectedField",
    "DoneResult",
    "detect_and_fill",
    "detect_fields",
    "fill_and_submit",
    "fill_field",
    "submit",
    "upload_file",
]

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_FAILURES = 5
# Not underscore-prefixed: providers.py (PHASE13.md step 5) waits on this
# same selector before calling detect_fields on a client-rendered page
# (Ashby's React app paints its form after `domcontentloaded` fires) --
# one shared definition of "a fillable field", not two that could drift.
FIELD_SELECTOR = "input:visible, select:visible, textarea:visible"

_CONFIRMATION_TIMEOUT_MS = 5000
_CONFIRMATION_POLL_MS = 200
# Researched, not assumed (PHASE14.md step 3): Greenhouse and Lever both
# redirect to a distinct, org-configurable confirmation/success URL after
# a real submit (support.greenhouse.io "Edit application confirmation
# page"; help.lever.co "Configuring your Lever-hosted Job Site"'s
# Application Success Page URL) -- a URL change is the dominant real
# signal for those two. Ashby's application form is a client-rendered
# SPA (developers.ashbyhq.com) with no guarantee of a URL change, so the
# phrase/submit-button checks below cover that case instead. None of
# these ever assume the local test fixture's own `id="confirmation"`.
_CONFIRMATION_PHRASES = (
    "thank you for applying",
    "application submitted",
    "application received",
    "received your application",
)


def _confirmation_signal_present(page: Page, apply_url: str) -> bool:
    """True if any of the three generic, ATS-agnostic confirmation
    signals is present right now: the URL moved away from the apply
    page, the submit control is gone, or a common confirmation phrase
    appears in the page's visible text."""
    if page.url != apply_url:
        return True
    if page.locator('button[type="submit"], input[type="submit"]').count() == 0:
        return True
    body_text = page.locator("body").inner_text().lower()
    return any(phrase in body_text for phrase in _CONFIRMATION_PHRASES)


def _wait_for_confirmation(page: Page, apply_url: str) -> bool:
    """Polls `_confirmation_signal_present` for up to
    `_CONFIRMATION_TIMEOUT_MS` -- real ATS pages take a moment to
    navigate or re-render after a submit click, the same real-world
    reason the old `wait_for_selector` call used a timeout."""
    deadline = time.monotonic() + (_CONFIRMATION_TIMEOUT_MS / 1000)
    while True:
        if _confirmation_signal_present(page, apply_url):
            return True
        if time.monotonic() >= deadline:
            return False
        page.wait_for_timeout(_CONFIRMATION_POLL_MS)


def detect_fields(page: Page) -> list[DetectedField]:
    """Real DOM query (visible input/select/textarea elements) cross-
    referenced against a real accessibility-tree snapshot — the hybrid
    grounding signal, not vision/screenshot-only and not raw-DOM-only.

    Radios collapse to one DetectedField per group (grouped by name=,
    the real HTML requirement for radios to behave as a group at all) —
    emitted after every other field, once every option's label is known.

    Snapshots `body`, not `form` (PHASE13.md step 4): a real Ashby
    application page has no `<form>` element at all — a React app
    rendering inputs directly — which made `page.locator("form")` hang
    for the full 30s timeout and raise. `body` is a strict superset of
    whatever a real `<form>` would contain, so this is a backward-
    compatible broadening, confirmed against the existing Greenhouse/
    Lever real-browser tests, not a behavior change for either.
    """
    ax_snapshot = page.locator("body").aria_snapshot()
    fields: list[DetectedField] = []
    radio_labels: dict[str, list[str]] = {}
    radio_selectors: dict[str, str] = {}

    for element in page.locator(FIELD_SELECTOR).all():
        name = element.get_attribute("name")
        element_id = element.get_attribute("id")
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        input_type = element.get_attribute("type") or "" if tag == "input" else ""
        if input_type in ("submit", "button", "hidden"):
            continue  # not a fillable field

        if input_type == "radio" and name:
            label = resolve_label(element)
            if label:
                radio_labels.setdefault(name, []).append(label)
            radio_selectors[name] = f'[name="{name}"]'
            continue

        if name:
            identifier, selector = name, f'[name="{name}"]'
        elif element_id:
            identifier, selector = element_id, f'[id="{element_id}"]'
        else:
            continue  # neither identifier is present -- can't be targeted later
        label = resolve_label(element)
        confirmed = bool(label) and f'"{label}"' in ax_snapshot
        fields.append(
            DetectedField(
                name=identifier,
                tag=tag,
                input_type=input_type,
                label=label,
                confirmed_by_ax_tree=confirmed,
                selector=selector,
            )
        )

    for name, labels in radio_labels.items():
        confirmed = any(f'"{label}"' in ax_snapshot for label in labels)
        fields.append(
            DetectedField(
                name=name,
                tag="input",
                input_type="radio",
                label=None,
                confirmed_by_ax_tree=confirmed,
                selector=radio_selectors[name],
                options=labels,
            )
        )

    logger.info("detect_fields: %d real fields found", len(fields))
    return fields


def detect_and_fill(
    page: Page,
    url: str,
    text_values: dict[str, str],
    file_values: dict[str, str],
) -> DetectAndFillResult:
    """Same detect -> fill/upload orchestration as fill_and_submit, but
    stops before the submit step entirely — structurally cannot cause a
    real submission, not just "chose not to this time". Used against
    real, live ATS pages (PHASE10.md step 8), where the only allowed
    verification is "detected and would-be-filled", never an actual
    click of a real submit button."""
    page.goto(url)
    fields = detect_fields(page)
    filled: list[str] = []
    failed: list[str] = []
    for field in fields:
        if field.input_type == "file":
            if field.name not in file_values:
                continue
            result = upload_file(page, field, file_values[field.name])
        else:
            if field.name not in text_values:
                continue
            result = fill_field(page, field, text_values[field.name])
        (filled if result.success else failed).append(field.name)
    return DetectAndFillResult(fields=fields, filled=filled, failed=failed)


def fill_and_submit(
    page: Page,
    url: str,
    text_values: dict[str, str],
    file_values: dict[str, str],
) -> DoneResult:
    """Orchestrates detect_fields -> fill_field*/upload_file -> submit,
    with a consecutive-failure cap, ending in an explicit, asserted
    done(success, reason) — never inferred from "no exception was
    raised." `text_values`/`file_values` are keyed by the real field
    `name=` attribute detect_fields() reports."""
    try:
        page.goto(url)
    except PlaywrightError as error:
        return DoneResult(success=False, reason=f"failed to load form: {error}")
    apply_url = page.url

    fields = detect_fields(page)
    if not fields:
        return DoneResult(success=False, reason="no fillable fields detected")

    consecutive_failures = 0
    for field in fields:
        if field.input_type == "file":
            if field.name not in file_values:
                continue
            result = upload_file(page, field, file_values[field.name])
        else:
            if field.name not in text_values:
                continue
            result = fill_field(page, field, text_values[field.name])

        if result.success:
            consecutive_failures = 0
            continue
        consecutive_failures += 1
        if consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
            return DoneResult(
                success=False,
                reason=(
                    f"stopped after {consecutive_failures} consecutive failures: {result.error}"
                ),
            )

    submit_result = submit(page)
    if not submit_result.success:
        return DoneResult(success=False, reason=f"submit failed: {submit_result.error}")

    if not _wait_for_confirmation(page, apply_url):
        return DoneResult(
            success=False, reason="no confirmation signal found on the page after submit"
        )

    return DoneResult(success=True, reason="submission confirmed")
