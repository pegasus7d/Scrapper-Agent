# Phase 10 — auto-apply

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 10's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]–[[docs/phases/PHASE9.md]]. Scoped
directly across a long conversation, not built from yet — the user
explicitly deferred the full feature twice ("this feature we will do
later," "this resume auto apply we will give later") while still refining
scope in discussion, then approved starting on a narrow, self-contained
first slice: a basic (v0) version that fills and submits a form we build
ourselves, using Playwright, before ever pointing automation at a real
company's real application form. **Only step 1 below is approved to
start.** Steps 2+ capture everything decided in conversation so it isn't
lost, but need a fresh go-ahead before any of them are built — this phase
crosses from "read public pages" (every source in this project so far)
into "submit write actions on third-party systems unattended," a
materially different risk category that deserves its own explicit
confirmation per step, not a blanket approval up front.

## Why step 1 is scoped the way it is

Two genuinely different questions were tangled together in the original
ask: *can this app reliably automate filling and submitting a form at
all* (a pure automation/engineering question, zero third-party risk) versus
*should that automation point at a real company's real ATS* (the actual
product/policy question, with real ToS and quality-control stakes). Step 1
answers only the first question, against a form this project fully
controls — no robots.txt, no ToS, no anti-bot risk, because nothing real is
being touched.

## Build order

1. **Basic (v0) local test-form fill-and-submit spike (backend).** Build a
   small, static local HTML test form — not a public form on the web,
   deliberately, to keep this fully private (text input, email, phone, a
   dropdown, a resume file-upload field, a textarea, a submit button; real
   field variety, not a trivial one-field form) — and a Playwright-driven
   routine that detects the fields, fills them from a hardcoded/test
   payload, uploads a real file, and submits, then confirms a real
   success state (e.g. a "Thanks, received" page the test form itself
   renders on submit). This is a spike to prove the mechanism, not a
   feature — no LLM-generated answers yet, no resume-Markdown grounding,
   no applicant profile; those get layered on once the base mechanism is
   trusted. Smoke: run it for real against the real local test form,
   confirm the submission actually lands (the test form should record or
   echo back what it received, not just return 200), re-run it a few
   times to confirm it isn't flaky before calling the mechanism trustworthy.

## Deferred — scoped but not approved to build (needs fresh confirmation)

The rest of this phase, as discussed and decided in conversation, kept
here so the scope isn't lost between sessions:

- **Fully autonomous submission** (not auto-fill-then-human-clicks) —
  explicitly chosen by the user, aware of the higher risk.
- **Greenhouse + Lever only, to start** — the two ATS providers this app
  already resolves companies against (`backend/scraper/resolve.py`), so
  there's real form structure to build against instead of guessing.
  External job boards that just link to arbitrary third-party apply pages
  are out of scope for this phase.
- **A real ToS check on Greenhouse's and Lever's automated-submission
  terms** — not just `robots.txt` — is the mandatory first step of the
  *real* (non-test-form) build, before any code touches either platform.
  This is the project's first write action against a third party rather
  than a read; every prior source only ever got a `robots.txt` check
  because reading public pages was all it ever did.
- **Resume ingestion stays as the existing PDF → Markdown flow**
  (`backend/resume.py`) — no Obsidian vault integration for this phase.
- **Resume upload gets extended with a small structured applicant
  profile**, captured once at upload time: current/expected salary,
  phone, work authorization, relocation, start-date availability. These
  are exactly the fields an LLM shouldn't guess at from resume text alone
  — wrong answers here (work authorization especially) can actively hurt
  an application rather than just look generic.
- **Match scoring gates auto-apply** — score discovered/scraped jobs
  against the resume's derived search positions; auto-apply only fires
  above a real threshold, not on every match.
- **Form-filler priority**: structured applicant-profile fields answer
  factual questions first; the existing LLM cascade (local → frontier
  escalation, same pattern as job/question extraction) only handles
  genuinely open-ended questions, grounded in resume Markdown + the
  specific job posting. Every answer logged per-application for later
  audit.
- **Safety controls**, treated as near-mandatory given full autonomy, not
  optional: a daily/per-run application cap (same pattern
  `MAX_ESCALATIONS_PER_RUN` already uses), a real kill switch to pause all
  auto-apply activity immediately, a company blocklist/allowlist,
  duplicate-application prevention across discovery sources, pacing/
  time-of-day spread instead of bursty submission.
- **Trust-building**: a per-application audit record (what was actually
  submitted, any LLM-generated answers, a snapshot of the confirmation
  page) and a dry-run mode (simulate N matches, show what would have been
  submitted, without a permanent per-application review gate).
- **Closing the loop** — the gap that started this whole discussion,
  automating apply without automating anything downstream: surface real
  interview questions (already scraped, already tied to companies) the
  moment a job's status flips to "interviewing" (two existing features,
  currently disconnected); some form of reply detection so `Job.status`
  updates when a company actually responds, instead of staying manual
  forever even after applying became automatic; outcome feedback — track
  which auto-applied jobs got real responses, feed that back into tuning
  the match-score threshold over time.

Next: step 1 only, once this file is committed on its own, per
WORKFLOW.md rule 3. Do not start on the deferred section without the user
re-confirming scope first.
