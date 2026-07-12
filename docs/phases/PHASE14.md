# Phase 14 — live application visibility, and three real bugs found testing it

Read [[docs/DESIGN.md]] first for the system contract; this file only holds
phase 14's step-by-step build order and rationale. See [[docs/WORKFLOW.md]]
for the recurring process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]-[[docs/phases/PHASE13.md]].

## Why this phase exists

Phase 13's own real end-to-end test — the first real application attempt
ever run against a real company (Checkr, Staff Software Engineer, via
`POST /applications` on the live app) — surfaced three real, concrete
problems, on top of the thing the user explicitly asked for:

**The user's ask: live visibility.** The Applications drawer
(`frontend/src/views/Applications.tsx`) fetches `GET /applications/{id}`
exactly once when opened (`useApi`, no live stream) — during the real
~30-90s async window while `plan_application_page_task`/
`execute_application_task` run on Huey, the drawer is a static snapshot
until manually reopened. This project already has a proven live-update
mechanism for exactly this shape (`GET /runs/stream` SSE +
`useRunsLive.ts`, phase 6) — extending it to applications is a natural
fit, not a new pattern.

**Bug 1 — the confirmation-detection check only recognizes the test
fixture.** `filler.py`'s `fill_and_submit` waits for
`page.wait_for_selector("#confirmation")` after a real submit click —
that id exists only on `test_form_server.py`'s own fake confirmation
page. Today's real Checkr attempt got `status=failed, error="no
confirmation element found after submit"` after a real `submit` click
succeeded — meaning this check would very likely misreport a genuinely
successful real submission as a failure too. Never actually verified
against any real ATS's real post-submit page.

**Bug 2 — the applicant profile has no name, email, LinkedIn, or
location fields at all.** Confirmed directly in today's real plan:
First Name, Last Name, Email, Country, City, and LinkedIn Profile all
came back `unanswered`, because `ApplicantProfile` only ever stored
phone/salary/work-authorization/relocation/start-date. A real
application is structurally incomplete without these, regardless of how
live the UI is.

**Bug 3 — `clean_html()` leaks script/style content into extraction
text.** Confirmed live: fetching a real WeWorkRemotely posting and
running it through `clean_html()` (the same function
`backend/whatsapp/intake.py` feeds the LLM) produced 49KB of "cleaned"
text, a large fraction of it raw, minified New Relic analytics
JavaScript. `_TAGS = re.compile(r"<[^>]+>")` strips `<script>`/`<style>`
*tags* but not their *content*. Every existing source
(Greenhouse/Lever/Ashby/etc.) only ever runs `clean_html()` on a small,
isolated JSON field value with no `<script>` tags in it at all, so this
never surfaced before — phase 13's WhatsApp single-URL intake is the
first thing in the codebase to run it against a real, whole HTML page,
and the first to hit it.

## Build order

1. **Fix `clean_html()`'s script/style leak (backend).** Strip
   `<script>...</script>` and `<style>...</style>` blocks — content
   included, not just the tags — before the existing generic tag
   stripper runs. Verify against the same real WeWorkRemotely posting
   used to find the bug: re-run `clean_html(page.raw)` and confirm the
   New Relic JS is gone and the output shrinks substantially. Confirm
   this is backward-compatible for every existing source (their JSON
   field snippets never had `<script>`/`<style>` tags to begin with, so
   this should be a no-op change for them) by re-running the existing
   Greenhouse/Lever/Ashby chunk-parsing tests unchanged. Investigate,
   but don't necessarily build yet: does `backend/whatsapp/intake.py`
   specifically still need a further, real content-extraction/
   readability step on top of this fix (isolating the actual job
   posting from nav/footer/ad boilerplate)? Test against 2-3 more real,
   varied job-posting pages and decide based on the real signal-to-noise
   measured, not assumed — only build the heavier step if this fix alone
   genuinely isn't enough.

2. **Extend the applicant profile with name/email/LinkedIn/location
   (backend + frontend).** New `ApplicantProfile` columns — a single
   `full_name` field (not separate first/last: real names don't always
   split into exactly two parts; the answer-tool splits naively at
   answer time for a form that wants separate first/last fields, an
   honest, documented limitation for compound/non-Western names rather
   than over-engineering a name parser), `email`, `linkedin_url`,
   `location`. One Alembic migration (vec0/FTS5 autogenerate false
   positives stripped by hand per existing convention, round-tripped
   against a scratch copy of `hirable.db` before the real
   `upgrade head`). New answer-tools in `answers.py`
   (`get_full_name`/`get_email`/`get_linkedin_url`/`get_location`),
   mirroring the existing `get_phone`-style pattern exactly. Wire the
   new fields into `ApplicantProfileIn`/`Out` and the Profile view's
   real form. Real smoke test: re-run a plan against the same real
   Checkr posting (job 147) or a fresh one with the profile now fully
   filled in, and confirm First Name/Last Name/Email/LinkedIn now
   resolve from the profile instead of coming back unanswered.

3. **Fix the confirmation-detection bug (backend).** Research first,
   without ever triggering a real, complete submission just to observe
   it (the submission gate stays sacred — this is investigated, not
   probed by actually submitting): what do Greenhouse/Lever/Ashby's own
   integration docs or third-party ATS-integration guides say about
   post-submission behavior (URL redirect, a confirmation page, inline
   SPA state change)? Replace the single hardcoded `#confirmation`
   selector with a more resilient, generic heuristic — e.g. any of: the
   page URL changing away from the apply URL, the submit button/form no
   longer being present, or a small set of common real confirmation
   phrases ("thank you for applying", "application submitted","received
   your application") appearing in the page's visible text — rather than
   one brittle id match that only ever existed on the local test
   fixture. Tests extend `test_form_server.py`'s existing confirmation
   page with realistic variation (a URL redirect instead of an id, a
   real confirmation phrase instead of `id="confirmation"`) to prove the
   new heuristic actually generalizes, not just re-passes the original
   fixture.

4. **Live application-progress backend (SSE).** `GET
   /applications/{id}/stream`, mirroring `stream.py`'s `run_updates`
   exactly (diff-based polling of the same payload
   `GET /applications/{id}` already returns, yielding a frame only when
   it actually changes) — registered in `routes_applications.py` before
   the existing `/applications/{application_id}` route, the same
   ordering `routes_runs.py` already uses so "stream" is never captured
   as a path parameter.

5. **Live application-progress frontend.** `useApplicationLive(id)`
   hook mirroring `useRunsLive.ts` (SSE primary, falls back to the
   existing poll on disconnect), wired into `ApplicationDrawer` in place
   of the current one-shot `useApi` call. A small live indicator (the
   same pulsing-dot pattern `RunProgressPanel.tsx` already uses) while
   the application is `pending` — mid-planning or mid-execution, not yet
   at a terminal status. `npm run build` clean (this project doesn't
   unit-test UI logic per `frontend/CLAUDE.md`, strict `tsc` is the
   gate).

6. **Real, combined end-to-end smoke test.** With all of the above
   landed: run a fresh, complete real application attempt (new
   applicant-profile fields filled in, so it's a genuinely complete
   plan this time) against a real, live posting, and actually watch the
   Applications drawer update live through planning, review the now-
   complete plan, and — only if the user personally chooses to, in the
   moment, exactly like every prior phase's submission gate — confirm
   it, watching the live view correctly detect and report the real
   outcome this time. Report the real, honest result either way.

Next: driven by `/loop` per [[docs/WORKFLOW.md]] once the user approves
this phase; stop at step 6.
