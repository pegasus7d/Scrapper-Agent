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

   **Done.** Added `_SCRIPT_STYLE_BLOCKS = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)`
   to `backend/scraper/sources/_base.py`, applied before the existing
   `_TAGS` stripper in `clean_html()`. Re-fetched the real WeWorkRemotely
   posting that originally surfaced the bug
   (`weworkremotely.com/remote-jobs/coin-market-cap-technical-ai-product-manager`,
   92,045 raw chars, 35 `<script>` tags): old logic produced 53,209
   cleaned chars with `newrelic` literally present in the output; new
   logic produces 5,551 clean chars with no analytics JS. Tested against
   two more real, varied pages to check generalization and decide on the
   readability-extraction question: a second WeWorkRemotely posting
   (98,593 → 8,315 chars, clean) and a real Greenhouse boards page
   (`job-boards.greenhouse.io/checkr`, 63,641 → 5,467 chars, clean). All
   three came back as mostly job-relevant text with only minor nav-menu
   boilerplate at the start (~5-10% of output) — good enough
   signal-to-noise for the LLM extractor as-is. Decision: the heavier
   readability/content-isolation step is **not** needed; the
   script/style fix alone is enough, based on this real measured
   evidence rather than assumption. Confirmed backward-compatible: all
   22 existing Greenhouse/Lever/Ashby tests in
   `tests/sources/jobs/test_companies.py` pass unchanged (their chunks
   are isolated JSON field values with no `<script>`/`<style>` tags, so
   the new regex is a no-op for them). Added
   `tests/sources/test_base.py` (7 new tests) covering the script/style
   strip, case-insensitivity, multiple blocks, and the no-op case for
   plain snippets. `./validate.sh` green (519 tests passed, mypy clean,
   ruff clean).

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

   **Done.** Added `full_name`/`email`/`linkedin_url`/`location` columns
   to `ApplicantProfile` (migration `59409f1af06f`, vec0/FTS5
   false-positive drops stripped by hand, round-tripped upgrade+downgrade
   against a scratch copy of `hirable.db` before the real `upgrade
   head`). Added six answer-tools to `answers.py`: `get_full_name`,
   `get_email`, `get_linkedin_url`, `get_location`, plus
   `get_first_name`/`get_last_name` (not in the original plan text, but
   needed in practice — a form asking for separate First/Last Name
   inputs needs its own tools, not just `get_full_name`; each does the
   documented naive split on the first whitespace run, e.g. "Maria Del
   Carmen Lopez" → first="Maria", last="Del Carmen Lopez"). Wired through
   `ApplicantProfileIn`/`Out`, `routes_profile.py`, and four new fields
   in the Profile view's form. Real smoke test: ran the actual planner
   (`planner.plan_application`, real Ollama cascade, real Playwright
   fetch of the live Checkr posting) against a scratch copy of
   `hirable.db` — never the real one, per PHASE10.md step 5's hard stop
   against inventing real applicant data — with a test profile filled
   in for every new field. Result: `application.status =
   awaiting_confirmation` (a complete plan, not `failed`). Confirmed the
   exact fields named in this step's own acceptance check now resolve
   from the profile instead of `unanswered`: `First Name*` → "Test"
   (source=profile), `Last Name*` → "Applicant", `Email*` →
   "test.applicant@example.com", `LinkedIn Profile*` →
   "https://linkedin.com/in/testapplicant". Also observed, out of this
   step's scope: `Phone*` still came back unanswered even with
   `profile.phone` set — the local LLM cascade didn't select the
   pre-existing `get_phone` tool for that field on this run, a cascade
   accuracy question unrelated to the new fields added here, not
   investigated further. `./validate.sh` green (526 tests passed, mypy
   clean, ruff clean, frontend build clean).

   **Also found and fixed along the way**: a real, unrelated bug in this
   project's own `.claude/settings.json` — the `PreToolUse` hook
   restricting `pre-commit-guard.sh` (which runs the full `validate.sh`
   and blocks on failure) to only `git commit *` commands had its `"if"`
   field nested at the wrong level (on the hook-group entry instead of
   inside the individual hook object), so it was silently ignored and
   the hook fired on *every* Bash command instead. Confirmed via a
   `claude-code-guide` agent that `if` is a real, supported field but
   must live inside the hook object; fixed with the user's explicit
   sign-off (a change to guardrail config, correctly blocked by the auto
   mode self-modification classifier until approved).

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

   **Done.** Researched real ATS post-submit behavior first (web search,
   not assumed): Greenhouse's own "Edit application confirmation page"
   docs and Lever's "Application Success Page URL" setting both confirm
   a real HTTP redirect to a distinct, org-configurable confirmation URL
   after submit; Ashby's application form is a client-rendered SPA
   (developers.ashbyhq.com) with no guaranteed URL change at all. That
   directly grounds the three-signal heuristic implemented in
   `filler.py`'s new `_confirmation_signal_present`/
   `_wait_for_confirmation`: the URL moved away from the apply page, OR
   the submit button/input is gone, OR the page's visible text contains
   one of a small set of real confirmation phrases ("thank you for
   applying", "application submitted", "application received",
   "received your application") — polled for up to 5s (the same timeout
   the old `wait_for_selector` used), replacing the single hardcoded
   `#confirmation` id match. The submission gate stayed sacred — every
   verification ran against local test fixtures, never a real ATS.
   `test_form_server.py`'s new fixtures (split into a new
   `test_form_server_confirmations.py` module to stay under CLAUDE.md's
   300-line cap) prove real generalization, not just a re-pass: a
   redirect-based confirmation with no id or phrase at all
   (Greenhouse/Lever's real shape), a same-URL SPA-style confirmation
   with a real phrase and no navigation (Ashby's real shape), and a
   negative-path fixture that gives no confirmation signal at all,
   proving the heuristic can still correctly report `success=False`
   rather than always succeeding. All three are real, live-browser tests
   (genuine Playwright + a real local uvicorn server, not mocked) — 3 new
   tests, `./validate.sh` green (529 tests passed, mypy clean, ruff
   clean, frontend build clean). The original `id="confirmation"`
   happy-path test still passes unchanged, now via the URL-change signal
   (the browser's real POST navigation to `/submit` changes `page.url`)
   rather than the id match specifically.

4. **Live application-progress backend (SSE).** `GET
   /applications/{id}/stream`, mirroring `stream.py`'s `run_updates`
   exactly (diff-based polling of the same payload
   `GET /applications/{id}` already returns, yielding a frame only when
   it actually changes) — registered in `routes_applications.py` before
   the existing `/applications/{application_id}` route, the same
   ordering `routes_runs.py` already uses so "stream" is never captured
   as a path parameter.

   **Done.** Added `application_updates()` to `stream.py`, mirroring
   `run_updates()`'s diff-based polling shape exactly (1s poll,
   `run_in_threadpool` for the blocking SQLAlchemy call, yields only on
   an actual payload change, ends the generator outright if the
   application no longer exists rather than polling forever). Extracted
   the `Application -> ApplicationOut` conversion (previously a private
   `_to_out` inside `routes_applications.py`) into a new shared
   `backend/api/application_view.py` so the SSE stream and the one-shot
   `GET /applications/{id}` produce byte-identical payloads from one
   definition, not two independently-maintained ones — avoided a
   circular import between `routes_applications.py` and `stream.py`
   this way. `GET /applications/{application_id}/stream` registered
   before `GET /applications/{application_id}` per the stated
   ordering convention. Also found and fixed in passing:
   `backend/api/dto.py` had already crossed CLAUDE.md's 300-line cap
   (310 lines, from step 2's new `ApplicantProfile` fields) — split the
   Application/kill-switch/company-block DTOs into a new
   `dto_applications.py` (its own small commit, since it's an unrelated
   fix). Real smoke test: ran the actual FastAPI app
   (`uvicorn --factory backend.api.main:create_app`) from a scratch
   working directory holding a copy of `hirable.db` — never the real
   one, since `config.DATABASE_FILE` is a relative path resolved
   against the process's cwd — created a real `pending` Application row
   for job 147 (Checkr), curled `/api/applications/5/stream` and got a
   real first frame back (`"status":"pending","company_name":"Checkr"`),
   then called `events.mark_awaiting_confirmation` on that row from a
   second process while the curl was still connected and watched a
   second, live frame arrive with `"status":"awaiting_confirmation"`
   and the real `planned_fields` payload, all within the same open SSE
   connection. 4 new tests in `test_stream.py` (yields current state,
   skips unchanged polls, yields again on a real status change, ends
   the stream for a nonexistent application) mirroring the existing
   `run_updates` test shapes. `./validate.sh` green (533 tests passed,
   mypy clean, ruff clean).

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
