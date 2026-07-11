"""Shared dataclasses and label resolution for the filler (PHASE10.md step
1, PHASE11.md step 3) — split out from `filler.py`/`filler_actions.py` to
break the circular import a single-file split would otherwise create
(detection needs the action functions' return types; actions need
`DetectedField` and label resolution), and to stay under CLAUDE.md's
300-line file cap.
"""

from dataclasses import dataclass

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator

# Real per-element label resolution, run in-page (Locator.evaluate) rather
# than round-tripping each attribute check through separate Playwright
# calls: a real <label for=id>, else a wrapping <label>, else aria-label,
# else placeholder — in that priority, confirmed directly against the
# real test form's markup.
LABEL_JS = """el => {
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


def resolve_label(locator: Locator) -> str | None:
    try:
        label = locator.evaluate(LABEL_JS)
    except PlaywrightError:
        return None
    return label.strip() if isinstance(label, str) and label.strip() else None


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
    # Real option labels for a radio group (e.g. ["Yes", "No"]); None for
    # every other field, including checkboxes (PHASE11.md step 3). Grouped
    # radios collapse to one DetectedField sharing the group's name= —
    # the answer-tool layer needs to see one Yes/No question, not two
    # separate, individually-meaningless fields.
    options: list[str] | None = None


@dataclass
class DoneResult:
    success: bool
    reason: str


@dataclass
class DetectAndFillResult:
    fields: list[DetectedField]
    filled: list[str]  # names of fields successfully filled/uploaded
    failed: list[str]  # names of fields that failed
