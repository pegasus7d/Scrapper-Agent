"""A local-only test form server (PHASE10.md step 1) — a real HTTP server
serving a real HTML form with real field variety (text, email, phone,
dropdown, file upload, textarea), used to prove out the Playwright-driven
fill-and-submit mechanism in `filler.py` before ever pointing it at a real
third-party ATS.

Deliberately never mounted on the real app (`backend.api.main.create_app`)
and never included in `docs/DESIGN.md` §4's API surface — this exists
purely to give the spike something real and fully private to interact
with. No `robots.txt`, no ToS, no anti-bot risk, because nothing real is
being touched (WORKFLOW.md rule 2 doesn't apply here for exactly that
reason).

Real fields, each with a real `<label for=...>` (not just a placeholder),
so `filler.py`'s label-resolution logic has genuine label markup to work
against — a trivial one-field or unlabeled form would prove nothing.
"""

from typing import Annotated

from fastapi import FastAPI, Form, UploadFile
from fastapi.responses import HTMLResponse

app = FastAPI(title="Hirable auto-apply test form (local only, PHASE10.md step 1)")

_FORM_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Test application form</title></head>
<body>
<h1>Apply to Test Company</h1>
<form method="post" action="/submit" enctype="multipart/form-data">
  <div>
    <label for="full_name">Full name</label>
    <input type="text" id="full_name" name="full_name" required>
  </div>
  <div>
    <label for="email">Email address</label>
    <input type="email" id="email" name="email" required>
  </div>
  <div>
    <label for="phone">Phone number</label>
    <input type="tel" id="phone" name="phone">
  </div>
  <div>
    <label for="role">Role applying for</label>
    <select id="role" name="role" required>
      <option value="">Select a role</option>
      <option value="backend">Backend Engineer</option>
      <option value="frontend">Frontend Engineer</option>
      <option value="fullstack">Full-Stack Engineer</option>
    </select>
  </div>
  <div>
    <label for="resume">Resume</label>
    <input type="file" id="resume" name="resume" required>
  </div>
  <div>
    <label for="cover_note">Anything else you'd like us to know?</label>
    <textarea id="cover_note" name="cover_note"></textarea>
  </div>
  <fieldset>
    <legend>Willing to relocate?</legend>
    <label><input type="radio" name="relocate" value="yes"> Yes</label>
    <label><input type="radio" name="relocate" value="no"> No</label>
  </fieldset>
  <div>
    <label for="remote_ok">
      <input type="checkbox" id="remote_ok" name="remote_ok" value="true">
      Open to fully remote roles
    </label>
  </div>
  <button type="submit">Submit application</button>
</form>
</body>
</html>
"""


# Simulates Greenhouse's real quirk (PHASE10.md step 8, PHASE11.md step
# 2): the application form is embedded on the page but hidden until a
# real "Apply" button click reveals it — never a separate URL.
_GREENHOUSE_LIKE_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Greenhouse-like posting</title></head>
<body>
<h1>Job at Greenhouse-like Co</h1>
<button type="button" id="apply_button"
        onclick="document.getElementById('gh-form').style.display='block'">Apply</button>
<form id="gh-form" style="display:none">
  <label for="first_name">First name</label>
  <input type="text" id="first_name" name="first_name">
</form>
</body>
</html>
"""

# Simulates Lever's real quirk: the job-description page has no form at
# all; the real application form lives at a distinct `/apply` URL.
_LEVER_LIKE_JOB_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Lever-like posting</title></head>
<body><h1>Job at Lever-like Co</h1><p>No form on this page.</p></body></html>
"""
_LEVER_LIKE_APPLY_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Lever-like apply</title></head>
<body>
<form>
  <label for="name">Full name</label>
  <input type="text" id="name" name="name">
</form>
</body></html>
"""


# Simulates Ashby's real quirk (PHASE13.md step 4): a distinct
# `/application` URL like Lever's, but with no `<form>` element at all —
# a React app rendering inputs directly in the page body, which is what
# broke `page.locator("form").aria_snapshot()` on the real live page.
_ASHBY_LIKE_JOB_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Ashby-like posting</title></head>
<body><h1>Job at Ashby-like Co</h1><p>No form on this page.</p></body></html>
"""
_ASHBY_LIKE_APPLICATION_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Ashby-like application</title></head>
<body>
<!-- Real timing bug this reproduces (PHASE13.md step 5): Ashby's actual
     application page is client-rendered, so its fields aren't in the DOM
     when `domcontentloaded` fires -- a fixed delay before the JS insert
     below is what makes this fixture prove the real fix, not just its
     structure. -->
<script>
setTimeout(() => {
  document.body.insertAdjacentHTML(
    "beforeend",
    '<label for="_systemfield_name">Legal Name</label>' +
    '<input type="text" id="_systemfield_name" name="_systemfield_name">'
  );
}, 300);
</script>
</body></html>
"""


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _FORM_HTML


@app.get("/apply", response_class=HTMLResponse)
def apply_alias() -> str:
    """A Lever-style /apply alias for the same real, fully-working form
    (PHASE11.md step 7) — the executor's own tests need a form reachable
    via prepare_application_page's real "lever" convention that also has
    a genuine, working /submit handler, unlike the read-only
    /lever-like/{id}/apply route step 2 added."""
    return _FORM_HTML


@app.get("/greenhouse-like", response_class=HTMLResponse)
def greenhouse_like() -> str:
    return _GREENHOUSE_LIKE_HTML


@app.get("/lever-like/{job_id}", response_class=HTMLResponse)
def lever_like_job(job_id: str) -> str:
    return _LEVER_LIKE_JOB_HTML


@app.get("/lever-like/{job_id}/apply", response_class=HTMLResponse)
def lever_like_apply(job_id: str) -> str:
    return _LEVER_LIKE_APPLY_HTML


@app.get("/ashby-like/{job_id}", response_class=HTMLResponse)
def ashby_like_job(job_id: str) -> str:
    return _ASHBY_LIKE_JOB_HTML


@app.get("/ashby-like/{job_id}/application", response_class=HTMLResponse)
def ashby_like_application(job_id: str) -> str:
    return _ASHBY_LIKE_APPLICATION_HTML


@app.post("/submit", response_class=HTMLResponse)
async def submit(
    full_name: Annotated[str, Form()],
    email: Annotated[str, Form()],
    role: Annotated[str, Form()],
    resume: UploadFile,
    phone: Annotated[str, Form()] = "",
    cover_note: Annotated[str, Form()] = "",
    relocate: Annotated[str, Form()] = "",
    remote_ok: Annotated[bool, Form()] = False,
) -> str:
    """Echoes back exactly what was received — real proof a submission
    landed, not just that the endpoint returned 200. `filler.py`'s smoke
    test reads these `id="received-*"` values back out of the real
    rendered page.

    Real bug caught by this file's own test suite, not shipped: plain
    `str` parameters on a POST route default to query params in FastAPI —
    only `UploadFile` is inferred as multipart on its own. Every text
    field needs an explicit `Form()` annotation, confirmed directly (a
    real `curl`/`httpx` POST returned 422 "missing: query.full_name"
    before this fix)."""
    resume_bytes = await resume.read()
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>Application received</title></head>
<body>
<h1 id="confirmation">Thanks, received</h1>
<dl>
  <dt>full_name</dt><dd id="received-full_name">{full_name}</dd>
  <dt>email</dt><dd id="received-email">{email}</dd>
  <dt>phone</dt><dd id="received-phone">{phone}</dd>
  <dt>role</dt><dd id="received-role">{role}</dd>
  <dt>cover_note</dt><dd id="received-cover_note">{cover_note}</dd>
  <dt>relocate</dt><dd id="received-relocate">{relocate}</dd>
  <dt>remote_ok</dt><dd id="received-remote_ok">{remote_ok}</dd>
  <dt>resume_filename</dt><dd id="received-resume_filename">{resume.filename}</dd>
  <dt>resume_size_bytes</dt><dd id="received-resume_size_bytes">{len(resume_bytes)}</dd>
</dl>
</body>
</html>
"""
