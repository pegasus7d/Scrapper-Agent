# Phase 11 — the application attempt pipeline

Read [[docs/DESIGN.md]] first for the system contract; this file only holds
phase 11's step-by-step build order and rationale. See [[docs/WORKFLOW.md]]
for the recurring process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]–[[docs/phases/PHASE10.md]].

## Why this phase exists

Phase 10 built every *component* of auto-apply — the Playwright filler with
hybrid grounding, the safety controls (kill switch, risk classification,
caps, pacing, dedup), the append-only event log, the structured applicant
profile, match-score gating, and the answer-tool system — but nothing
composes them. There is no way to run "an application attempt" today: no
orchestrator, no API endpoint, no UI. The submission gate PHASE10.md
defines can't even be reached, because nothing walks up to it.

Phase 11 builds the walk-up. At the end of this phase, a full application
attempt runs end-to-end as one observable, replayable pipeline — safety
checks → match gate → real field detection → answered plan → risk
classification → **paused at `awaiting_confirmation`** — and the user can
review exactly what would be submitted (every field, every answer, every
answer's source) and confirm or reject it in the UI. The submit executor
lands fully wired but is only ever exercised against step 1's local test
form during the build; **the first real submission happens only when the
user personally clicks Confirm on a real, reviewed application** — which
is precisely the "explicit, in-the-moment confirmation" PHASE10.md's
submission gate requires. The autonomous loop building this phase never
issues that confirmation itself, under any circumstances.

## The plan/execute split (the one real architecture decision)

A naive pipeline would fill the live form, then pause for confirmation —
but a paused attempt would have to hold a real browser page open
indefinitely while waiting for a human, across a Huey task boundary. That
doesn't survive contact with reality.

Instead the pipeline is two passes, mirroring OpenHands' propose → confirm
→ execute shape (phase 10's own prior-art research):

- **Plan** (autonomous, cannot submit): open the real page read-only,
  detect fields, produce an answer per field via the answer-tool system,
  classify risk, persist the complete per-field plan on the `Application`
  row, close the browser, set `awaiting_confirmation`. No fill happens; no
  page is left open.
- **Execute** (confirmation-triggered only): fresh browser session,
  re-detect fields, verify the live field set still matches the stored
  plan (**fail safe on any drift** — abort and mark failed rather than
  filling a form that changed since review), fill, attach the resume,
  submit, verify real confirmation-page state, record everything through
  the event log.

One extra safety rule on top of `SUBMIT_CONFIRMATION_POLICY`: **until the
first real submission has ever succeeded, every attempt pauses for
confirmation regardless of policy** — the policy ("risky" default) only
starts governing after the gate has been crossed once, exactly as
PHASE10.md's submission-gate section already states.

## Real gaps from phase 10's own smoke tests that this phase closes

Each of these is a real, observed finding from PHASE10.md's step write-ups,
not a guess:

1. **Resume upload is stateless** — PDF in, Markdown out, nothing
   persisted (PHASE7.md step 2's design, fine until now). Auto-apply needs
   the actual PDF file to attach to a real form, and the Markdown to
   ground answer-tools without re-uploading per attempt.
2. **Lever's real form has radio buttons** (`cards[…]` yes/no fields,
   found in step 8's live investigation) — the filler handles
   input/select/textarea/file, but `Locator.fill()` does not work on a
   radio or checkbox.
3. **Provider-specific page preparation**: Lever's form lives at
   `<posting>/apply` (a distinct URL); Greenhouse's is embedded on the
   posting page but hidden until a real "Apply" button click (both found
   the hard way in step 8).
4. **`MATCH_SCORE_THRESHOLD` is an uncalibrated guess** — step 6's real
   smoke test showed a genuinely relevant resume/job pair scoring 0.48,
   under the 0.5 default, partly from a language mismatch. The user needs
   real score distributions over their own data to tune it, not a
   constant picked in the dark.

## Build order

1. **Persist the resume (backend).** Extend `POST /resume` to also save
   the uploaded PDF bytes to a real file (`data/resume.pdf`, gitignored —
   binary on the filesystem, not a DB blob) and the converted Markdown
   onto the single-row `ApplicantProfile` (new nullable
   `resume_markdown` column, one Alembic migration — remember
   `server_default` is unnecessary for a nullable column, and strip the
   vec0/FTS5 autogenerate false positives as every prior migration has).
   `GET /profile` gains a real `has_resume` signal so the UI can show
   whether an attempt is even possible. Existing stateless behavior
   (return the Markdown) is unchanged.
   **Done.** `config.RESUME_STORAGE_PATH` (`data/resume.pdf`, gitignored)
   + `resume.save_resume_pdf()`; `ApplicantProfile.resume_markdown`
   (migration `82281bf711fc`, both directions verified against the real
   dev DB) + `profile.save_resume_markdown()` — a narrow update touching
   only that one column, so a resume re-upload never clobbers
   phone/salary/etc. the way a full `save_profile()` call would.
   `ApplicantProfileOut` gained `has_resume` (derived from
   `resume_markdown is not None`, built explicitly in the route rather
   than via `model_validate`, since it isn't a real ORM column). A real
   bug caught before it shipped: `save_resume_pdf`'s `path` parameter must
   be read from `config` at the call site, not relied on as the
   function's own default — a default is bound once at import time, so a
   test monkeypatching `config.RESUME_STORAGE_PATH` would silently miss
   it. 17 real tests across `test_resume.py`/`test_api_resume.py`/
   `test_autoapply_profile.py`.
   **Testing infrastructure change requested mid-step**: the user asked
   for a fixed, reusable test resume file instead of a throwaway
   synthetic PDF regenerated (and discarded) every time — added
   `tests/fixtures/resume-backend.pdf` (a checked-in, synthetic "Backend
   Engineer" persona, not real personal data) and a shared
   `tests/conftest.py::resume_pdf_bytes` fixture, replacing every
   per-file `_minimal_pdf_bytes()` helper and the `.txt` placeholder
   `test_autoapply_filler.py` used for its own upload tests.
   Real smoke test (real backend, real dev DB, the real fixture file via
   `curl`): `GET /profile` correctly showed `has_resume: false` before
   upload and `true` after; the real file landed at `data/resume.pdf`.
   Per the same "stop generating and discarding" intent, **this smoke
   test's resume was deliberately left persisted** rather than reset
   afterward (unlike every prior phase's smoke-test cleanup) — later
   steps in this phase (the planner, the executor) need a real resume
   already available to build and test against, and the fixture's
   content is clearly a synthetic test persona, not a claim about the
   user's real background. `pytest` (425 passed) / `mypy` / `ruff check`
   / `ruff format --check` / `npm run build` all green.

2. **Provider page preparation (backend).** New
   `backend/autoapply/providers.py`: `prepare_application_page(page,
   ats_provider, posting_url)` navigates to the real form — Lever: go to
   `<posting>/apply`; Greenhouse: go to the posting and click the real
   "Apply" button (`get_by_role("button", name="Apply", exact=True)`,
   verified working in step 8's smoke test). Per-provider quirks isolated
   in one module, never spread through the filler. Unknown provider is a
   real error, not a silent fallthrough.
   **Done.** `UnknownProvider` (bad `ats_provider` value) and
   `PagePreparationFailed` (a known provider whose expected structure
   isn't found, e.g. no real Apply button) are kept as two distinct
   exceptions — a bad input and a broken assumption about live markup are
   different failure modes. `test_form_server.py` gained
   `/greenhouse-like` (a real hidden-until-clicked form) and
   `/lever-like/{id}` + `/lever-like/{id}/apply` (a real two-page split)
   so this is testable without touching a live third party in the
   permanent suite — 4 real tests
   (`tests/test_autoapply_providers.py`). Real smoke test against the
   same live Greenhouse (`checkr`) and Lever (`theathletic`) postings
   step 8 used: `prepare_application_page` reproduced the exact same real
   field counts step 8 found by hand (17 Greenhouse, 26 Lever), with
   `page.url` confirmed unchanged for Greenhouse and confirmed to be the
   real `/apply` URL for Lever — no `submit()` call anywhere in this
   step's code path. `pytest` (429 passed) / `mypy` / `ruff check` /
   `ruff format --check` all green.

3. **Radio/checkbox support in the filler (backend).** `detect_fields`
   already reports `input_type="radio"`; `fill_field` grows a real branch:
   radios are selected by matching the wanted value against each option's
   resolved label (`check()`), checkboxes by boolean. Grouped radios
   (same name, N labels) collapse to one `DetectedField` carrying its real
   option labels — the answer-tool layer needs to see "Yes/No" as the
   valid answers, not two separate fields. Tested against an extended
   local test form (add a radio group and a checkbox to
   `test_form_server.py`), not against a real ATS.
   **Done.** `detect_fields` now groups radios by their shared `name=`
   (the real HTML requirement for radios to behave as a group at all)
   into one `DetectedField` with an `options: list[str]` (e.g.
   `["Yes", "No"]`); `fill_field` grew a checkbox branch (truthy/falsy
   string → `check()`/`uncheck()`) and a radio branch (matches `value`
   against each option's real resolved label, `check()`s the matching
   one, raises a real `ValueError` — caught and reported as a normal
   `ActionResult` failure — when nothing matches). `test_form_server.py`
   gained a real radio group ("Willing to relocate?") and checkbox
   ("Open to fully remote roles") so this is testable end-to-end without
   touching a live ATS. **File-size cap crossed and fixed**:
   `filler.py` hit 314 lines with these additions — split into
   `filler_types.py` (dataclasses + label resolution, needed by both
   sides), `filler_actions.py` (the per-field action functions), and
   `filler.py` (detection + orchestration, re-exporting the public names
   so existing callers are unaffected) — a naive two-file split would
   have created a circular import (`fill_field` needs `DetectedField`,
   `detect_fields` needs `fill_field`), which the shared `filler_types`
   module resolves. 4 new real tests (`tests/test_autoapply_filler.py`).
   Real smoke test against the same live Lever posting PHASE10.md step 8
   used: the 8 previously-fragmented individual radio inputs that
   investigation found now correctly collapse into 6 real `Yes`/`No`
   groups, and `fill_field` successfully selected an option — no
   `submit()` call anywhere in this step's code path. `pytest` (433
   passed) / `mypy` / `ruff check` / `ruff format --check` all green.

4. **Match-score calibration (backend + frontend).** `GET
   /profile/match-scores`: embeds the stored resume Markdown once (422 if
   none saved), scores every job that has a stored embedding via the same
   `vec_distance_cosine` step 6 uses, returns `(job, score)` sorted. A
   small section in the Profile view renders the distribution against the
   current threshold so the user can see — on their real data — what 0.5
   would gate out, and `MATCH_SCORE_THRESHOLD` gets tuned from evidence
   (a config change with the reasoning documented) if the real
   distribution says so.
   **Done — real, positive calibration result.**
   `matching.score_all_jobs()` embeds the resume once (not once per job,
   unlike `gate()`/`compute_match_score()`) and scores every job with a
   stored embedding; `GET /profile/match-scores` (422 with no resume
   uploaded) joins the scores back to real `Job` rows and returns them
   sorted, highest first, alongside the current threshold.
   `MatchScoreSection` in the Profile view fetches this (skipped
   entirely, not just unrendered, until `has_resume` is true) and shows
   how many of the scraped jobs clear the threshold plus the top 10 with
   pass/fail badges. 4 new backend tests
   (`tests/test_autoapply_matching.py`, `tests/test_api_profile.py`).
   Real smoke test against the actual dev DB (102 real jobs with stored
   embeddings, the real persisted resume left in place from step 1): real
   scores ran **0.44–0.72** — every one of the top 5 was a genuinely
   relevant software-engineering role (Staff/Senior Software Engineer at
   Checkr, a Senior Full Stack Engineer role), and only 3 of 102 fell
   below the 0.5 default, all three genuinely irrelevant (a financial
   controller, a founder's associate, a media marketing manager). Unlike
   step 6's single-pair test (which found one relevant pair scoring just
   under threshold), this real, comprehensive distribution shows 0.5
   correctly separating relevant from irrelevant roles for this resume —
   **`MATCH_SCORE_THRESHOLD` left unchanged at 0.5**, a real evidence-
   based decision, not an untested guess either way. `pytest` (437
   passed) / `mypy` / `ruff check` / `ruff format --check` /
   `npm run build` all green.

5. **The planner (backend).** `backend/autoapply/planner.py`:
   `plan_application(session, job)` composes, in order: kill switch →
   company blocked → dedup → daily cap → pacing → match gate →
   `start_application` → `prepare_application_page` → `detect_fields`
   (read-only — **no fill in this pass at all**) → one answer per field
   via `answers.answer_field` (profile tools win; LLM fallback; honest
   `unanswered` entries stay unanswered) → `classify_risk` (first
   application to this company → high) → persist the full per-field plan
   as a JSON column on `Application` (new `planned_fields` column, same
   `JSON`-column precedent as `Run.errors`; one migration) → status
   `awaiting_confirmation` → close the browser. Every action through the
   event log. **This function is structurally incapable of submitting** —
   it never calls `fill_field`, `upload_file`, or `submit` on a real page.
   **Done.** Every pre-flight gate (kill switch, unresolved provider,
   blocked company, dedup, daily cap, pacing, no resume, match score)
   raises a real, typed exception *before* any `Application` row is
   created — no partial/broken row for a rejected pre-flight check.
   `is_first_application_to_company` is computed before
   `start_application` creates this attempt's own row (afterward, "any
   application exists for this company" would always be true). Risk
   classification's `llm_confidence` uses a real, simple proxy: any
   open-ended LLM-sourced answer makes the whole plan uncertain (fails
   safe to high); a genuinely unanswered field doesn't, since it's a
   different, less risky situation (no data, not a guess). A structural
   test (`test_planner_has_no_way_to_fill_or_submit`) asserts the module
   doesn't even import `fill_field`/`upload_file`/`submit`/
   `detect_and_fill`/`fill_and_submit` — 13 tests total
   (`tests/test_autoapply_planner.py`), against `test_form_server.py`'s
   Greenhouse-like/Lever-like routes, a scripted fake LLMClient.
   **A real incident occurred and was fixed during this step**: testing
   the new `planned_fields` migration's downgrade against the live
   `hirable.db` (this project's own established discipline until now)
   silently corrupted the unrelated `job_embeddings` vec0 table's shadow
   tables — confirmed by comparing against the backup taken immediately
   before, which had `job_embeddings` fully intact. Recovered by
   restoring that backup (with the user's explicit confirmation first,
   since overwriting the live DB is irreversible) and re-applying the
   migration once, cleanly. `CLAUDE.md` now documents the fix: round-trip
   migration tests must run against a scratch copy via `alembic -x
   db_url=sqlite:////tmp/scratch.db <command>` (the real override key
   `migrations/env.py` documents — an earlier attempt using `-x
   sqlalchemy.url=...` silently did nothing and nearly caused a second
   incident before the real key was found), never against `hirable.db`
   directly.
   Real smoke test against the same live Checkr/Greenhouse posting used
   throughout this phase, with the real persisted resume: real
   navigation, real 17-field detection matching step 8's own finding,
   real per-field LLM answer attempts (real Ollama calls, one
   `answer_field:<label>` event per field), correctly classified `"high"`
   risk (first application to this company), correctly reached
   `awaiting_confirmation` with `finished_at` still unset. Every field
   came back `unanswered` — a real, honest, *correct* outcome: the real
   profile has no data filled in yet (deliberately reset in step 1), and
   the local model's documented conservative behavior (step 7's own
   finding) means it declines to guess rather than fabricate an answer.
   Smoke-test `Application`/`ApplicationEvent` rows deleted afterward.
   `pytest` (450 passed) / `mypy` / `ruff check` / `ruff format --check`
   all green.

6. **Attempt API + task wiring (backend).** `routes_applications.py` +
   one Huey task, mirroring the run endpoints exactly: `POST
   /applications {job_id}` (409 if another attempt is active — same
   one-at-a-time rule runs already enforce), `GET /applications`, `GET
   /applications/{id}` (row + full event replay + the stored plan), `POST
   /applications/{id}/reject` (terminal, records the event), `POST
   /applications/{id}/confirm` (records the confirmation event and
   triggers step 7's executor), `GET/POST /autoapply/kill-switch`, `POST
   /companies/{id}/auto-apply-block` toggle.
   **Done.** `planner.py` split into `check_preflight` (fast, pure-DB —
   kill switch, provider resolution, blocklist, dedup, daily cap,
   pacing, resume, match gate) and `run_page_planning` (the real,
   slow browser work) so the route runs the former synchronously (a real
   422 with the actual reason, immediately) and enqueues the latter via
   `backend/autoapply/tasks.py`'s `plan_application_page_task` — the
   same fast-sync/slow-async split `backend.scraper.tasks` already uses
   for scrape runs. `safety.active_application_exists` (checks
   `status == "pending"`) is the 409 guard — rows already sitting at
   `awaiting_confirmation` don't block a new plan; only concurrent
   *planning* does. `GET /applications/{id}` returns the row and its full
   event replay together — the confirmation-review UI (step 8) needs
   both at once. 13 real API tests
   (`tests/test_api_applications.py`), the real Huey task functions faked
   the same way `test_api.py` already fakes `run_scrape_task`.
   Real smoke test against the real dev DB: `POST /applications` against
   the real Checkr job ran every real pre-flight gate (a real Ollama
   embed call, a real match-gate pass) and created a genuine `"pending"`
   row, confirmed to stay `"pending"` with the consumer disabled (proving
   the task is truly enqueued, not run inline); reject, the kill switch,
   and the company-block toggle all verified against real DB state and
   reverted afterward. **Confirm's actual execution was deliberately not
   smoke-tested against any real, ATS-linked row** — enqueuing real
   execution work against a real Greenhouse posting, even accidentally,
   is exactly the risk this phase's gate discipline exists to prevent;
   the executor's own dedicated, local-only test suite (step 7) already
   covers that path for real. `pytest` (468 passed) / `mypy` / `ruff
   check` / `ruff format --check` all green.

7. **The executor (backend).** `backend/autoapply/executor.py`:
   `execute_submission(session, application)` — refuses unless status is
   `awaiting_confirmation` with a recorded confirmation event and the
   kill switch is off; fresh browser session; `prepare_application_page`;
   re-detect; **verify the live field set against the stored plan and
   fail safe on any drift**; fill each planned field; attach
   `data/resume.pdf`; `submit()`; verify real confirmation-page state;
   status `submitted` or `failed` with the error recorded; every action
   through the event log. **Gate discipline for the build loop: this
   step's tests and smoke test run against the local test form only.**
   The executor is never pointed at a real ATS by the loop — the only
   path to a real submission is a real human clicking Confirm in step
   8's UI, and this phase's loop never does that.
   **Done — built ahead of step 6, since step 6's confirm endpoint
   needs a real executor to call.** The drift check compares the exact
   *set* of field names between the stored plan and a fresh
   `detect_fields()` call — any real change to the live form since
   review (a field added, removed, or renamed) fails the application
   safe rather than filling a form nobody actually reviewed. Only fields
   the plan actually answered get filled (an unanswered field is left
   blank, same convention `detect_and_fill` already uses); file fields
   attach the real, persisted resume from `config.RESUME_STORAGE_PATH`
   regardless of the plan's own answer text for that field (the text is
   just the "should this be filled" signal, e.g. `"resume-backend.pdf"`
   — the real bytes always come from the one persisted file). A known,
   honestly-documented limitation: confirmation-page verification is
   currently tuned to the local test form's own `#confirmation` element;
   a real ATS's confirmation-page shape is unknown until the submission
   gate is separately crossed, and generalizing this check is real,
   future work at that point, not solved here.
   Added a `/apply` alias to `test_form_server.py` serving the same
   real, fully-working form — the executor's own tests need a route
   reachable through `prepare_application_page`'s real "lever" `/apply`
   convention that also has a genuine, working `/submit` handler, unlike
   the read-only `/lever-like/{id}/apply` route step 2 added.
   5 real tests (`tests/test_autoapply_executor.py`), including a real
   happy-path run that genuinely fills every field type (text, select,
   file upload, radio, checkbox) and submits against the local server,
   confirmed via the real rendered confirmation page — never against a
   real ATS, per this step's own explicit gate discipline. `pytest` (455
   passed) / `mypy` / `ruff check` / `ruff format --check` all green.

8. **Applications view (frontend).** New nav view mirroring the
   established table+drawer pattern: attempts list (status/risk badges),
   a drawer with the full event replay, the kill-switch toggle, and — for
   `awaiting_confirmation` rows — the review screen: every planned field
   with its label, the exact value that would be entered, and a source
   badge (`profile` / `llm` / `unanswered`), plus Confirm and Reject
   buttons. This screen *is* the submission gate's required record of
   "exactly what's about to happen" — the user sees the complete
   would-be submission before the one irreversible click.

9. **Real end-to-end dry-run (validation, no new code).** Run the real
   pipeline — `POST /applications` against one real Lever job and one
   real Greenhouse job from the dev DB — through to
   `awaiting_confirmation`. Verify the stored plan's contents against
   the real form fields step 8's investigation already catalogued, verify
   the event replay reads as a coherent story, verify both rows sit
   correctly reviewable in the UI, then **Reject both** (or leave them
   awaiting the user — but never Confirm). Report the real plans back to
   the user. **The loop stops here.** Crossing the gate — the first real
   Confirm — is the user's own action, taken in the UI, whenever they
   have filled in their real profile and are actually ready to apply to
   that specific job.

## What the user must do before the first real Confirm (not build steps)

- Fill in the real applicant profile (Profile view) — phase 10's hard
  stop still holds: nothing invents this data.
- Re-upload the resume once after step 1 lands, so the PDF is persisted
  for attachment.
- Look at step 4's real score distribution and tune
  `MATCH_SCORE_THRESHOLD` if the evidence says so.
- Gmail reply-detection stays gated on OAuth credentials only the user
  can create (PHASE10.md step 9's write-up has the setup path) — out of
  this phase's scope entirely.

Next: steps 1-9 above are the build order. Driven by `/loop` per
[[docs/WORKFLOW.md]] once the user approves this phase; stop at step 9,
and stop immediately if the only remaining action would be issuing a real
confirmation — that click belongs to the user alone.
