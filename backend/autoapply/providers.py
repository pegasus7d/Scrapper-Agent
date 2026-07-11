"""Provider-specific page preparation (PHASE11.md step 2) — isolates each
ATS's real quirks (found the hard way in PHASE10.md step 8's live
investigation) in one module, never spread through the generic filler:
Lever's real application form lives at a distinct `/apply` URL, separate
from the job-description page; Greenhouse's is embedded on the posting
page but stays hidden until a real "Apply" button click.

Ashby (PHASE13.md step 4, live-investigated the same way): its real
application form lives at a distinct `{posting_url}/application` URL,
Lever's shape rather than Greenhouse's — every field is already visible
on load, no button click needed. A real, separate finding from this same
investigation lives in `filler.py`'s `detect_fields` docstring instead
(Ashby's page has no `<form>` element at all), since it's a shared-filler
fix, not provider-specific navigation.

Known real limitation, not fixed here: Ashby's custom Yes/No questions
render as `<button>` elements and its location field as a custom
combobox, neither a native `<input>`/`<select>` — `detect_fields`'s DOM
query doesn't see them at all, so they're silently absent from a planned
Ashby application today (confirmed directly against a real posting,
PHASE13.md step 4's own "Done." writeup has the full field list found vs.
missed). Native fields (name/email/phone/resume/LinkedIn/free-text
questions) detect and would fill correctly; button-based custom
questions are a real, separate capability this step doesn't add.
"""

from typing import Literal

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

_GREENHOUSE_APPLY_BUTTON = "Apply"
# domcontentloaded, not the default "load": Greenhouse's real page has a
# long-lived embedded iframe (a Google API proxy, found in step 8's
# investigation) that never fully settles, network-idle-style waits, or
# "load" itself in some runs.
_GOTO_WAIT_UNTIL: Literal["domcontentloaded"] = "domcontentloaded"


class UnknownProvider(Exception):
    """Raised for any ats_provider other than "greenhouse"/"lever" — a
    real error, never a silent fallthrough to unsupported markup."""


class PagePreparationFailed(Exception):
    """Raised when a known provider's expected page structure isn't
    found (e.g. no real "Apply" button on a Greenhouse posting) — a real,
    distinct failure from an unrecognized ats_provider value."""


def prepare_application_page(page: Page, ats_provider: str, posting_url: str) -> None:
    """Navigate `page` to the real, live application form for one posting.

    Real, provider-specific navigation, confirmed against live postings in
    PHASE10.md step 8 — never a generic "go to posting_url" for both.
    """
    if ats_provider == "lever":
        page.goto(f"{posting_url}/apply", wait_until=_GOTO_WAIT_UNTIL)
        return
    if ats_provider == "greenhouse":
        page.goto(posting_url, wait_until=_GOTO_WAIT_UNTIL)
        _click_greenhouse_apply(page)
        return
    if ats_provider == "ashby":
        # Lever's shape, not Greenhouse's: a distinct URL, every field
        # already visible on load, confirmed live (PHASE13.md step 4) —
        # {jobUrl}/application is exactly the real applyUrl the Ashby API
        # itself returns for every posting sampled.
        page.goto(f"{posting_url}/application", wait_until=_GOTO_WAIT_UNTIL)
        return
    raise UnknownProvider(f"no page-preparation logic for ats_provider={ats_provider!r}")


def _click_greenhouse_apply(page: Page) -> None:
    button = page.get_by_role("button", name=_GREENHOUSE_APPLY_BUTTON, exact=True)
    try:
        button.first.click(timeout=5000)
    except PlaywrightError as error:
        raise PagePreparationFailed(
            f"Greenhouse posting has no real 'Apply' button to reveal the form: {error}"
        ) from error
