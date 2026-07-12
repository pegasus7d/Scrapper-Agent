"""Confirmation-shape fixtures (PHASE14.md step 3) — split out of
`test_form_server.py` to stay under CLAUDE.md's 300-line cap. Proves
`filler.py`'s confirmation heuristic generalizes past the original
`id="confirmation"` fixture, not just re-passes it: a real HTTP redirect
(Greenhouse/Lever's real shape, researched via their own docs — see
`filler.py`'s own comment for the citations) with no special id or
phrase, a client-rendered SPA confirmation phrase with no URL change at
all (Ashby's real shape), and a negative-path fixture that gives no
confirmation signal.
"""

from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse, RedirectResponse

router = APIRouter()

_REDIRECT_FORM_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Redirect-style application form</title></head>
<body>
<h1>Apply to Redirect Co</h1>
<form method="post" action="/redirect-submit">
  <label for="full_name">Full name</label>
  <input type="text" id="full_name" name="full_name" required>
  <button type="submit">Submit application</button>
</form>
</body>
</html>
"""

_REDIRECT_THANKS_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>All set</title></head>
<body><p>All set -- we'll be in touch.</p></body>
</html>
"""

_PHRASE_FORM_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>SPA-style application form</title></head>
<body>
<h1>Apply to SPA Co</h1>
<form id="spa-form">
  <label for="full_name">Full name</label>
  <input type="text" id="full_name" name="full_name" required>
  <button type="submit">Submit application</button>
</form>
<script>
document.getElementById("spa-form").addEventListener("submit", (event) => {
  event.preventDefault();
  document.body.innerHTML = "<p>Thank you for applying to SPA Co.</p>";
});
</script>
</body>
</html>
"""

# Deliberately gives no confirmation signal at all after "submit" -- the
# negative-path fixture proving the heuristic doesn't just always report
# success.
_STUCK_FORM_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Stuck application form</title></head>
<body>
<h1>Apply to Stuck Co</h1>
<form id="stuck-form">
  <label for="full_name">Full name</label>
  <input type="text" id="full_name" name="full_name" required>
  <button type="submit">Submit application</button>
</form>
<script>
document.getElementById("stuck-form").addEventListener("submit", (event) => {
  event.preventDefault();
});
</script>
</body>
</html>
"""


@router.get("/redirect-form", response_class=HTMLResponse)
def redirect_form() -> str:
    return _REDIRECT_FORM_HTML


@router.post("/redirect-submit")
async def redirect_submit(full_name: Annotated[str, Form()]) -> RedirectResponse:
    """A real HTTP redirect to a distinct confirmation URL -- Greenhouse/
    Lever's real post-submit shape, no `id="confirmation"` involved."""
    return RedirectResponse(url="/redirect-thanks", status_code=303)


@router.get("/redirect-thanks", response_class=HTMLResponse)
def redirect_thanks() -> str:
    return _REDIRECT_THANKS_HTML


@router.get("/phrase-form", response_class=HTMLResponse)
def phrase_form() -> str:
    return _PHRASE_FORM_HTML


@router.get("/stuck-form", response_class=HTMLResponse)
def stuck_form() -> str:
    return _STUCK_FORM_HTML
