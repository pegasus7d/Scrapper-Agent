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

3. **Radio/checkbox support in the filler (backend).** `detect_fields`
   already reports `input_type="radio"`; `fill_field` grows a real branch:
   radios are selected by matching the wanted value against each option's
   resolved label (`check()`), checkboxes by boolean. Grouped radios
   (same name, N labels) collapse to one `DetectedField` carrying its real
   option labels — the answer-tool layer needs to see "Yes/No" as the
   valid answers, not two separate fields. Tested against an extended
   local test form (add a radio group and a checkbox to
   `test_form_server.py`), not against a real ATS.

4. **Match-score calibration (backend + frontend).** `GET
   /profile/match-scores`: embeds the stored resume Markdown once (422 if
   none saved), scores every job that has a stored embedding via the same
   `vec_distance_cosine` step 6 uses, returns `(job, score)` sorted. A
   small section in the Profile view renders the distribution against the
   current threshold so the user can see — on their real data — what 0.5
   would gate out, and `MATCH_SCORE_THRESHOLD` gets tuned from evidence
   (a config change with the reasoning documented) if the real
   distribution says so.

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

6. **Attempt API + task wiring (backend).** `routes_applications.py` +
   one Huey task, mirroring the run endpoints exactly: `POST
   /applications {job_id}` (409 if another attempt is active — same
   one-at-a-time rule runs already enforce), `GET /applications`, `GET
   /applications/{id}` (row + full event replay + the stored plan), `POST
   /applications/{id}/reject` (terminal, records the event), `POST
   /applications/{id}/confirm` (records the confirmation event and
   triggers step 7's executor), `GET/POST /autoapply/kill-switch`, `POST
   /companies/{id}/auto-apply-block` toggle.

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
