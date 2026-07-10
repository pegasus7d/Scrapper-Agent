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
"""

import logging
from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_FAILURES = 5
_FIELD_SELECTOR = "input:visible, select:visible, textarea:visible"
_SUBMIT_SELECTOR = 'button[type="submit"], input[type="submit"]'

# Real per-element label resolution, run in-page (Locator.evaluate) rather
# than round-tripping each attribute check through separate Playwright
# calls: a real <label for=id>, else a wrapping <label>, else aria-label,
# else placeholder — in that priority, confirmed directly against the
# real test form's markup.
_LABEL_JS = """el => {
    if (el.id) {
        const byFor = document.querySelector(`label[for="${el.id}"]`);
        if (byFor && byFor.textContent.trim()) return byFor.textContent.trim();
    }
    const wrapping = el.closest('label');
    if (wrapping && wrapping.textContent.trim()) return wrapping.textContent.trim();
    const ariaLabel = el.getAttribute('aria-label');
    if (ariaLabel) return ariaLabel;
    const placeholder = el.getAttribute('placeholder');
    return placeholder || null;
}"""


@dataclass
class ActionResult:
    success: bool
    error: str | None = None


@dataclass
class DetectedField:
    # The real, stable per-field identifier: the HTML name= attribute when
    # present, else id (PHASE10.md step 8's own real finding — Greenhouse's
    # embedded application form has no name= attribute on any field at all,
    # a React form submitted via JS rather than a native HTML POST; id is
    # real and stable there instead, not a rare fallback case).
    name: str
    tag: str  # "input" | "select" | "textarea"
    input_type: str  # e.g. "text", "email", "tel", "file"; "" for select/textarea
    label: str | None
    # Cross-referenced against a real accessibility-tree snapshot (not just
    # trusting the DOM-computed label alone) — the actual hybrid-grounding
    # signal, confirmed True/False per field, not assumed.
    confirmed_by_ax_tree: bool
    # The real Playwright selector to target this field with — computed
    # once at detect time from whichever of name/id was actually present,
    # rather than re-derived (and reassumed to be name=) at fill time.
    selector: str


@dataclass
class DoneResult:
    success: bool
    reason: str


def _resolve_label(locator: Locator) -> str | None:
    try:
        label = locator.evaluate(_LABEL_JS)
    except PlaywrightError:
        return None
    return label.strip() if isinstance(label, str) and label.strip() else None


def detect_fields(page: Page) -> list[DetectedField]:
    """Real DOM query (visible input/select/textarea elements) cross-
    referenced against a real accessibility-tree snapshot — the hybrid
    grounding signal, not vision/screenshot-only and not raw-DOM-only."""
    ax_snapshot = page.locator("form").aria_snapshot()
    fields: list[DetectedField] = []
    for element in page.locator(_FIELD_SELECTOR).all():
        name = element.get_attribute("name")
        element_id = element.get_attribute("id")
        if name:
            identifier, selector = name, f'[name="{name}"]'
        elif element_id:
            identifier, selector = element_id, f'[id="{element_id}"]'
        else:
            continue  # neither identifier is present -- can't be targeted later
        tag = element.evaluate("el => el.tagName.toLowerCase()")
        input_type = element.get_attribute("type") or "" if tag == "input" else ""
        if input_type in ("submit", "button", "hidden"):
            continue  # not a fillable field
        label = _resolve_label(element)
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
    logger.info("detect_fields: %d real fields found", len(fields))
    return fields


def fill_field(page: Page, field: DetectedField, value: str) -> ActionResult:
    try:
        locator = page.locator(field.selector)
        if field.tag == "select":
            locator.select_option(value)
        else:
            locator.fill(value)
        return ActionResult(success=True)
    except PlaywrightError as error:
        logger.warning("fill_field failed for %r: %s", field.name, error)
        return ActionResult(success=False, error=str(error))


def upload_file(page: Page, field: DetectedField, file_path: str) -> ActionResult:
    try:
        page.locator(field.selector).set_input_files(file_path)
        return ActionResult(success=True)
    except PlaywrightError as error:
        logger.warning("upload_file failed for %r: %s", field.name, error)
        return ActionResult(success=False, error=str(error))


def submit(page: Page) -> ActionResult:
    try:
        page.locator(_SUBMIT_SELECTOR).first.click()
        page.wait_for_load_state("networkidle")
        return ActionResult(success=True)
    except PlaywrightError as error:
        logger.warning("submit failed: %s", error)
        return ActionResult(success=False, error=str(error))


@dataclass
class DetectAndFillResult:
    fields: list[DetectedField]
    filled: list[str]  # names of fields successfully filled/uploaded
    failed: list[str]  # names of fields that failed


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

    try:
        page.wait_for_selector("#confirmation", timeout=5000)
    except PlaywrightError:
        return DoneResult(
            success=False, reason="no confirmation element found on the page after submit"
        )

    return DoneResult(success=True, reason="submission confirmed")
