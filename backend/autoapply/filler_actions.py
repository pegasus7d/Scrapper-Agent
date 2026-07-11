"""Real per-field actions against a live page (PHASE10.md step 1,
PHASE11.md step 3) — split out from `filler.py` (detection/orchestration)
to stay under CLAUDE.md's 300-line file cap; see `filler_types.py`'s own
docstring for why the dataclasses/label-resolution live in a third module.
"""

import logging

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page

from backend.autoapply.filler_types import ActionResult, DetectedField, resolve_label

logger = logging.getLogger(__name__)

_SUBMIT_SELECTOR = 'button[type="submit"], input[type="submit"]'
_CHECKBOX_TRUTHY_VALUES = {"true", "yes", "1"}


def _set_checkbox(locator: Locator, value: str) -> None:
    if value.strip().lower() in _CHECKBOX_TRUTHY_VALUES:
        locator.check()
    else:
        locator.uncheck()


def _select_radio_option(page: Page, field: DetectedField, value: str) -> None:
    """Radios in a group all share `field.selector` (matches every option
    in the group) — resolve each option's own label and check the one
    matching `value`, same label-resolution logic detect_fields used."""
    normalized_value = value.strip().lower()
    for option in page.locator(field.selector).all():
        label = resolve_label(option)
        if label and label.strip().lower() == normalized_value:
            option.check()
            return
    raise ValueError(f"no radio option matching {value!r} (available: {field.options})")


def fill_field(page: Page, field: DetectedField, value: str) -> ActionResult:
    try:
        locator = page.locator(field.selector)
        if field.tag == "select":
            locator.select_option(value)
        elif field.input_type == "checkbox":
            _set_checkbox(locator, value)
        elif field.input_type == "radio":
            _select_radio_option(page, field, value)
        else:
            locator.fill(value)
        return ActionResult(success=True)
    except (PlaywrightError, ValueError) as error:
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
