# Phase 10 — auto-apply

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 10's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]–[[docs/phases/PHASE9.md]]. Scoped
directly across a long conversation — the user explicitly deferred the
full feature twice ("this feature we will do later," "this resume auto
apply we will give later") while still refining scope in discussion,
approved starting on a narrow, self-contained first slice (step 1 — done),
then, once real prior-art and market research was folded in, authorized
building the rest directly ("invoke the loop and implement this"). **Steps
2-9 are now approved**, with two real, hard stops marked inline (real
applicant data only the user can provide; Gmail OAuth setup only the user
can grant) and **one gate that stays separate no matter what**: nothing in
this authorization causes a real application to be submitted to a real
company — the first real submission is its own explicit checkpoint (see
"The submission gate" below), not bundled into "implement this," because
that one action is categorically different from everything else in this
phase (irreversible, visible to a real company, the entire reason this
phase has had a stricter approval bar than every prior phase in this
project).

## Why step 1 is scoped the way it is

Two genuinely different questions were tangled together in the original
ask: *can this app reliably automate filling and submitting a form at
all* (a pure automation/engineering question, zero third-party risk) versus
*should that automation point at a real company's real ATS* (the actual
product/policy question, with real ToS and quality-control stakes). Step 1
answers only the first question, against a form this project fully
controls — no robots.txt, no ToS, no anti-bot risk, because nothing real is
being touched.

## Prior art checked (real, cited research — not guessed)

Six real open-source projects were researched in depth (real source read via
`gh api`/WebFetch, not README-skimming) specifically for patterns applicable
to this phase — browser-use, OpenHands, Crawl4AI, Dify, Langflow, Open
WebUI. Findings below are cited to real files/classes found in each repo at
research time; some (Dify, Langflow) are mid-refactor, so exact file paths
may drift — the *patterns* are what's being borrowed, not literal code.

- **browser-use** (`browser-use/browser-use`) — the closest real prior art
  to step 1 itself: an LLM-driven browser agent. Real, verified findings:
  DOM grounding is a **hybrid**, not vision-only and not raw-HTML-only —
  `DomService` (`dom/service.py`) merges the Chrome DevTools Protocol's DOM
  tree, Accessibility tree, and DOMSnapshot into one `EnhancedDOMTreeNode`
  tree, then `ClickableElementDetector.is_interactive()`
  (`dom/serializer/clickable_elements.py`) filters it down to a compact,
  indexed list of real interactive elements (`[index] <tag> text`) fed to
  the LLM as text, with a screenshot as a secondary/optional cross-check —
  not the primary grounding mechanism. Failed actions never crash the
  loop: `Tools.act()` wraps each action in a timeout, catches errors, and
  returns an `ActionResult(error=...)` fed back to the LLM as observation
  text, with a `consecutive_failures` cap (default 5) that forces a safe
  stop. Task completion is an **explicit contract**, not inferred: the
  model must emit a `DoneAction(success: bool, text)` — the agent never
  just "runs out of actions" and assumes success. `Browser(allowed_domains=
  [...])` restricts navigation scope, with a runtime warning if
  `sensitive_data` is set without a domain lock-down.
- **OpenHands** (`OpenHands/software-agent-sdk`, the successor to
  `All-Hands-AI/OpenHands`'s agent core) — the closest real prior art to
  *safety controls around autonomous action-taking*, the most directly
  relevant repo to this phase's deferred safety section. Real, verified
  findings: a `SecurityRisk` enum (LOW/MEDIUM/HIGH/UNKNOWN,
  `security/risk.py`) attached to every proposed action, with a pluggable
  `ConfirmationPolicy` (`AlwaysConfirm`/`NeverConfirm`/`ConfirmRisky
  (threshold=HIGH)`, `security/confirmation_policy.py`) —
  `SecurityAnalyzerBase.should_require_confirmation()` **fails safe to
  HIGH** if risk analysis itself errors, never fails open. When a risky
  action is proposed, the run loop sets status to
  `WAITING_FOR_CONFIRMATION` and halts *before* executing it — the pending
  action sits unexecuted until a second call approves it, or
  `reject_pending_actions(reason=...)` cancels just that one action (a
  real, granular kill switch, not just a global stop). Every action and
  its result is a persisted, timestamped, parent/child-linked `Event`
  (`event/base.py`) in an append-only log — the real audit trail
  mechanism. Browser actions are **discrete and typed**
  (`BrowserNavigateAction`, `BrowserGetStateAction`,
  `BrowserClickAction(index)`, `BrowserTypeAction(index, text)`), never
  one opaque "fill and submit the form" call, and each carries MCP-style
  `ToolAnnotations` (`destructiveHint`, `idempotentHint`) — a machine-
  readable risk signal per action type, not per task. Two hard caps run
  every loop iteration: `max_iteration_per_run` (a step-count ceiling) and
  `max_budget_per_run` (a USD spend ceiling), plus a separate
  `StuckDetector` for repetition/loop patterns.
- **Crawl4AI** (`unclecode/crawl4ai`) — checked honestly, real finding: **it
  doesn't apply here.** It's an article/content-extraction and markdown-
  conversion library (`markdown_generation_strategy.py`,
  `content_filter_strategy.py`); its schema-driven extraction
  (`JsonCssExtractionStrategy`) is built for repeated content rows
  ("a product card"), not form-field semantics — no input-type detection,
  no label-to-input association, and its markdown conversion would
  actively destroy the attributes a form-filler needs preserved. Its one
  real interaction capability (`CrawlerRunConfig.js_code`/`wait_for`/
  `session_id` for multi-step JS-driven pages) is a raw-JS escape hatch,
  not a form-aware API — the `session_id` + `wait_for`-before-scanning
  *pattern* is worth mirroring conceptually for multi-page ATS flows, but
  there's no Crawl4AI code to actually reuse. Don't revisit this one
  without new evidence.
- **Dify** (`langgenius/dify`) — real prior art for pipeline/workflow
  structure. Workflows are a real graph-as-data (`graph_topology.py`:
  explicit `nodes`/`edges` lists), executed against one shared, namespaced
  variable pool every node reads/writes (`variable_pool_initializer.py`,
  `{{#node.field#}}`-style interpolation) rather than strict per-edge
  input/output contracts — closer to a shared context object than a pure
  functional pipeline. `workflow_as_tool/` lets a whole saved workflow be
  exposed as a callable tool, so agents and workflows compose both ways.
  **Real, notable finding that cuts against this phase's own "fully
  autonomous" decision**: Dify ships a first-class `human_input` node
  *type* in its workflow node catalog — pausing a workflow for human
  review is treated as a normal pipeline primitive, not a bolted-on
  afterthought. Flagged here deliberately, not silently acted on (see
  "Open question" below).
- **Langflow** (`langflow-ai/langflow`) — checked honestly, real
  "overkill" verdict for this phase: its `Component`/`Graph` engine
  (`Output.types`/`Input.input_types` as string tags, `topological_sort()`
  DAG execution, `sorted_vertices_layers()` for parallel layers) is real
  and works, but it's a heavy, UI-coupled framework (Pydantic-model field
  objects carrying display metadata, an event/tracing/telemetry system,
  secret-masking) built to serve an arbitrary user-composed graph from a
  visual builder — disproportionate for this phase's fixed, known 6-8 step
  sequence. The one cheap, worth-keeping idea: lightweight string-tag
  input/output compatibility (`produces: list[str]` / `consumes:
  list[str]` on each pipeline step, checked at construction time) without
  any of the surrounding graph-engine machinery.
- **Open WebUI** (`open-webui/open-webui`) — real, directly reusable
  prior art for the applicant-profile "answer this question" tool system.
  `convert_function_to_pydantic_model()` (`utils/tools.py`) builds a
  Pydantic model — and from it, a real OpenAI function-calling JSON
  schema — from a plain Python function's type hints and docstring alone
  (reST-style `:param name: desc` parsing), no special decorator needed.
  Real, clean separation: **Tools** are callables the LLM decides to
  invoke mid-conversation (via the real function-calling API, not
  prompt-injected text — works with both Ollama and Claude tool-calling);
  **Functions** are a distinct, separate concept — admin-wired pipeline
  middleware (filters/pipes/actions) that isn't LLM-invoked at all.
  Per-tool **valves** (admin-level and per-user, encrypted) separate
  runtime config from the tool's logic.

### Real-world market validation (live products, not just architecture)

Checked directly, not guessed: how real, shipping auto-apply products
handle the exact submit-autonomy question this phase already resolved
above. Real, cited findings, not vibes:

- **Simplify** (a well-funded, widely-used real competitor) deliberately
  does **not** auto-submit — it autofills Greenhouse (~90% accuracy),
  Lever (~90%), Ashby (~80%), Workday (~70%), but a human clicks submit
  every time. The most successful real product in this exact space made
  the same call this phase's `SUBMIT_CONFIRMATION_POLICY` decision
  reaches for by default (`risky`), independently.
- **LazyApply and Sonara**, by contrast, do fully auto-submit, and it has
  real, documented consequences: LinkedIn actively detects "human-
  impossible velocity," and roughly 23% of automation users get account-
  restricted within 90 days. LazyApply specifically appears on public
  lists of blacklisted LinkedIn automation tools.
- **Real, reassuring finding specific to this project's own plan**: apps
  that submit directly to an ATS (Greenhouse/Lever) carry meaningfully
  less risk than apps that automate a platform's own UI (LinkedIn Easy
  Apply) — exactly the distinction this phase already made when scoping
  to Greenhouse+Lever rather than LinkedIn.

Net effect: this is real market evidence, independent of the OpenHands/
Dify architecture signal above, pointing the same direction — `risky` as
the default `SUBMIT_CONFIRMATION_POLICY`, not `never`, correlates with
what the most successful real competitor ships; full, unreviewed
auto-submission is the choice correlated with real, observed account-
restriction consequences in the wild (for LinkedIn-targeting tools
specifically — Greenhouse/Lever direct submission is a real, different,
lower-risk category, but "no safety valve at all" is still the riskier
end of the spectrum among real products either way).

### Real tooling for closing the loop's reply-detection piece

Checked directly for the one piece of "closing the loop" (below) that
has a real, non-obvious tooling question: how does an app detect that a
company replied to an application (rejection, interview invite) without
the user manually updating status?

- **Real open-source prior art doing exactly this already exists** —
  worth a closer look before designing from scratch, same discipline as
  the six-repo dive above: `Tomiwajin/CareerSync` (Gmail-integrated,
  pattern-matches inbox into Applied/Interview/Rejected/Offer, stateless/
  zero-storage by design), `JustAJobApp/jobseeker-analytics` (Gmail-
  connected dashboard), `tatevmane/Job-App-Tracker` (regex+NLP over
  Gmail). None have been read in depth yet — flagged as real candidates
  for the same kind of research pass the six repos above got, if/when
  this deferred item is approved.
- **Access**: the real **Gmail API** (official, free, OAuth) is the right
  fit for a single-user local tool like Hirable — not Nylas or Unipile,
  which are paid, multi-tenant email APIs built for platforms reading
  *many users'* mailboxes at once (normalized webhooks across Gmail/
  Outlook/IMAP); genuinely the wrong tool for one person's own inbox.
  `simplegmail` is a real, thin Python wrapper around the Gmail API worth
  using over raw `google-api-python-client` OAuth boilerplate.
- **Classification** (is this email a rejection, an interview invite, or
  noise?): the real, consistent choice is reusing Hirable's *existing*
  two-tier LLM cascade (Ollama local → Claude escalation, already doing
  this exact kind of judgment call for job/question extraction and
  resume-position derivation) — not a new NLTK/TextBlob keyword-or-
  sentiment pipeline, which is what most of the open-source trackers
  above actually use. Higher quality, zero new ML dependency, consistent
  with everything else this app already does.
- **`email-reply-parser`** (Zapier's real, real-world-tested library) is a
  small, genuinely useful addition — strips quoted thread history before
  an email reaches the LLM classifier, so it sees only the new content,
  not the entire back-and-forth.

### Decision: what actually gets adopted from this research

Reviewed with the user directly, resolved per idea rather than left as an
open question — adopt / adopt-as-configurable-default / skip, and why:

**Adopted outright** (cheap, clearly worth it, already reflected in this
file): browser-use's hybrid grounding + `ActionResult` + explicit `done`
contract (step 1's design, below); OpenHands' dual hard caps, stuck-
detection, and append-only typed audit event log (a natural extension of
this project's own `Run` row pattern, not a new concept); OpenHands'
discrete typed action space (step 1's design, below); Open WebUI's type-
hint+docstring→schema pattern for the applicant-profile answer tools, kept
cleanly separate from any logging/redaction middleware (Tools-vs-Functions
split); Dify's shared-context-object pattern for the pipeline (one
namespaced row per application attempt every step reads/writes — again,
confirms a shape this project's pipeline already uses elsewhere, not new
work).

**Skipped, with reasons, not silently dropped**: Crawl4AI (genuinely
doesn't apply — no form-aware extraction); Langflow's actual graph/DAG
engine (real "overkill" verdict from its own research — a fixed, known
6-8 step sequence doesn't need a runtime graph executor); the lightweight
string-tag step-compatibility idea *also* downgraded from a real
requirement to a nice-to-have — for a sequence this fixed, tests catch a
mis-wired pipeline more cheaply than a runtime tag-checker would; Dify's
`workflow_as_tool` (not needed until the pipeline is genuinely complex
enough to want sub-workflows-as-tools, not this phase); Open WebUI's
"valves" concept (that's solving a multi-user admin/per-user config
problem — Hirable is single-user, and `config.py` already plays that role
here).

**Adopted as a configurable default, not a silent override of the user's
full-autonomy choice**: OpenHands' fail-safe-to-HIGH risk gate and Dify's
`human_input` primitive both independently point at *some* risk-based
pause mechanism even in autonomous systems. Real resolution: a
`SUBMIT_CONFIRMATION_POLICY` setting with three real values —
`always` / `risky` / `never` — defaulting to **`risky`** (auto-fill
everything; pause only the final `submit` action, and only when it's
genuinely high-risk: first-ever application to this company, or an
LLM-answered question below a confidence threshold). `never` reproduces
exactly the fully-autonomous behavior already chosen; `risky` is the
recommended default, not a forced override — set `never` at any time to
match the original decision exactly. Risk classification itself must fail
safe to "treat as risky" on any classifier error, mirroring OpenHands'
own fail-safe-to-HIGH design, never fail open into a silent auto-submit.

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
   trusted.
   Real design decisions informed by the prior-art research above, not
   arbitrary: (a) **field detection uses a DOM+accessibility-tree scan**
   (Playwright's `page.accessibility.snapshot()` plus a visible-element
   DOM query), producing an indexed list of real fillable elements —
   mirrors browser-use's hybrid grounding, not a screenshot/vision-only
   approach, since it's cheaper and more reliable for the mostly-standard
   form controls ATS platforms use. (b) **every fill/click action returns
   a structured result** (`success: bool`, `error: str | None`) instead of
   raising on failure — mirrors browser-use's `ActionResult` pattern —
   with a small consecutive-failure cap that stops the run cleanly rather
   than hanging. (c) **completion is an explicit, asserted contract**: the
   routine itself must report `done(success: bool, reason: str)` after
   submitting, verified against the test form's real confirmation state —
   never inferred from "no exception was raised." (d) actions stay
   **discrete and typed** (`detect_fields`, `fill_field`, `upload_file`,
   `submit`), not one opaque `fill_and_submit_form()` call — mirrors
   OpenHands' discrete browser action space — so a later phase can attach
   a risk tag to the `submit` action specifically without redesigning
   everything else.
   Smoke: run it for real against the real local test form,
   confirm the submission actually lands (the test form should record or
   echo back what it received, not just return 200), re-run it a few
   times to confirm it isn't flaky before calling the mechanism trustworthy.
   **Done — step 1 complete, this phase's currently-approved scope is
   finished.** New `backend/autoapply/` package: `test_form_server.py`
   (a real FastAPI app, deliberately never mounted on the real app or
   listed in DESIGN.md §4 — text/email/tel/select/file/textarea fields,
   each with a real `<label for=...>`, a real `/submit` handler that
   echoes back exactly what it received) and `filler.py` (the discrete,
   typed `detect_fields`/`fill_field`/`upload_file`/`submit` routine plus
   the `fill_and_submit` orchestrator, exactly as designed above). Added
   `playwright` as an explicit direct dependency (pinned to 1.61.0, the
   version already present transitively via `scrapling[fetchers]` →
   `camoufox` — relying on that transitively was fragile, a scrapling bump
   could drop it).
   Two real bugs caught by this step's own test suite, not shipped, not
   assumed away: (1) `page.accessibility.snapshot()` — the exact API named
   in this step's own design text above — **does not exist** in the
   installed Playwright 1.61.0; confirmed directly by running it before
   writing `detect_fields()`, not assumed from older docs/tutorials.
   Real, current replacement used instead: `Locator.aria_snapshot()`,
   confirmed to correctly resolve every real `<label for=...>` in the test
   form, and — a genuinely useful, non-obvious real finding — Chromium's
   own accessibility tree exposes a file `<input>` as `button "Resume"`,
   not `textbox`, which the hybrid cross-reference in `detect_fields()`
   correctly accounts for. (2) FastAPI treats a plain `str` POST parameter
   as a query parameter by default — only `UploadFile` is inferred as
   multipart on its own; a real `httpx` POST against the real endpoint
   returned a real `422` ("missing: query.full_name") before every text
   field in `test_form_server.py`'s `/submit` handler got an explicit
   `Form()` annotation.
   Smoke, in two layers: (a) the automated suite
   (`tests/test_autoapply_filler.py`) is itself real end-to-end — a real
   uvicorn server in a background thread, a real headless-Chromium
   browser, no mocking, since Playwright needs a genuine socket a
   `TestClient` can't provide — 4/4 real tests pass, including a real
   "re-run three times, confirm no flakiness" case and a real unreachable-
   URL failure case. (b) A second, fully standalone smoke test outside
   pytest entirely, matching this project's usual discipline: a real
   uvicorn process started by hand, `filler.fill_and_submit` run against
   it via a bare script — real submission confirmed (`DoneResult(success=
   True, reason='submission confirmed')`), real file upload confirmed (a
   real 47-byte file, real filename preserved through to the confirmation
   page), re-run three more times with zero flakiness. A real negative
   case was also confirmed, not just the happy path: submitting with no
   values filled correctly reports `success=False` — the browser's own
   native `required`-field validation blocks the actual submission
   client-side, the page never reaches `/submit`, and `done()` correctly
   reports failure rather than inferring success from "the click didn't
   raise an exception."

## Steps 2+ — approved to build, with one explicit gate before any real submission

The user authorized building this scope directly ("invoke the loop and
implement this"). Sequenced into real build-order steps below, in
dependency order, not the unordered scope-list this section used to be.
**One gate stays in place regardless**: nothing in steps 2-9 below ever
causes a real application to be submitted to a real company. The first
time this app would actually click "submit" on a genuine Greenhouse/Lever
posting is its own separate, explicit checkpoint (marked below), not
bundled into this authorization — that single action is categorically
different from everything else here (irreversible, visible to a real
company, the entire reason this phase has had a stricter approval bar than
every prior phase). Steps that need something only the user can provide
(real applicant data, Gmail OAuth credentials) are marked as real, hard
stops, not routed around.

2. **Real ToS check on Greenhouse's and Lever's automated-submission
   terms (research, no code).** Not just `robots.txt` — the mandatory
   first step before any code touches either platform, per this project's
   own stated discipline for its first write-action against a third
   party. Read both platforms' actual terms; if either is silent/vague
   rather than an explicit prohibition, document that honestly and
   continue (per the user's stated risk tolerance); if either explicitly
   prohibits automated submission, stop and flag it as a real blocker
   before any further step touches that platform specifically.
   **Done — real, decisive, asymmetric finding.** `robots.txt` alone
   (already checked in PHASE7.md) was insufficient and stayed permissive
   for both (`boards.greenhouse.io` only disallows `/embed/`;
   `job-boards.greenhouse.io` and `jobs.lever.co` are both fully open) —
   the real answer lived in each platform's actual legal terms, not
   robots.txt, exactly as this step's own text anticipated.
   **Greenhouse: a real, explicit prohibition, found by reading the
   actual document, not assumed.** Greenhouse's "My Greenhouse User
   Agreement" (`my.greenhouse.io/users/agreement`), Section 3(z): users
   agree they will not "use automated means, including spiders, robots,
   crawlers, or similar means or processes to access or use the
   Services." This is a direct, explicit prohibition on exactly the class
   of automation this phase builds — not a vague timesharing/reverse-
   engineering clause aimed at competitors, a specific, named ban on
   bots/crawlers/automated means. Per this step's own stated criteria
   ("if either explicitly prohibits automated submission, stop and flag
   it as a real blocker before any further step touches that platform
   specifically"): **Greenhouse is excluded from automated submission
   for the rest of this phase, pending the user's explicit review of this
   finding** — not routed around, not narrow-scoped away on an untested
   theory that this agreement might only cover the separate "My
   Greenhouse" candidate-profile product rather than the general
   application flow. Read-only activity (the company/job scraping this
   project already does against `boards-api.greenhouse.io` since
   PHASE7.md) is unaffected — this finding is specific to *automated
   submission*, a materially different, unaddressed-until-now risk
   category.
   **Lever: no explicit prohibition found.** Lever's general Terms of
   Service (`lever.co/terms-of-service/`) is a customer/subscription
   agreement (governs companies paying for Lever, not job applicants) and
   is silent on automated access. No separate candidate/applicant terms
   document with an automation clause was found. Documented honestly as
   "silent, not a green light" per this step's own framing — proceeding
   with Lever is a real, informed choice, not a false "explicitly
   permitted" claim.
   **Resolution: the user reviewed this finding directly and explicitly
   chose to proceed with both Greenhouse and Lever**, accepting the real
   risk of violating Greenhouse's explicit anti-automation clause (the
   same category of real-world consequence LazyApply/Sonara hit with
   LinkedIn — see "Real-world market validation" above) rather than
   narrowing to Lever-only. Recorded here as an explicit, informed
   decision, not a risk quietly absorbed or argued away — step 8 (real
   ATS form-structure investigation) and everything beyond it proceeds
   against both platforms as originally scoped.
3. **`SUBMIT_CONFIRMATION_POLICY` + safety-control infrastructure
   (backend).** The `always`/`risky`/`never` setting (default `risky`),
   a `risk` tag on the discrete `submit` action from step 1's filler
   (fail-safe-to-HIGH on any classifier error), a daily/per-run
   application cap (`MAX_ESCALATIONS_PER_RUN`'s pattern), a real kill
   switch, a company blocklist/allowlist, duplicate-application
   prevention, pacing/time-of-day spread, OpenHands' dual hard-cap
   pattern (`max_iteration_per_run` + `max_budget_per_run`), and a
   `StuckDetector`-style repetition check. Pure infrastructure — no real
   ATS interaction yet, fully buildable and testable against step 1's
   local test form.
4. **Append-only audit event log (backend).** Mirrors this project's own
   `Run` row pattern, not a new concept: one persisted, timestamped,
   parent/child-linked event per action (propose → execute → observe),
   giving a genuine per-application replay rather than a final-outcome
   summary. Buildable and testable now, independent of any real
   submission ever happening.
5. **Structured applicant profile (backend + frontend).** New fields on
   resume upload: current/expected salary, phone, work authorization,
   relocation, start-date availability. **Real, hard stop on real data**:
   this step builds the schema, the endpoint, and the upload-time UI —
   it does *not* fill in your actual phone number, salary, or work-
   authorization status, since only you have that. The feature is usable
   the moment you fill it in yourself; nothing downstream that reads this
   profile can be meaningfully tested end-to-end with real values until
   you do.
6. **Match-score gating pipeline (backend).** A real gate step (score →
   threshold → proceed/skip) against the resume's derived search
   positions, structured as one shared, namespaced context object per
   application attempt (Dify's pattern, not Dify itself) — not an
   implicit if-statement. A real threshold value gets proposed and is
   tunable, not fixed in code.
7. **Form-filler answer-tool system (backend).** Structured-profile
   lookups (`get_phone`, `get_salary_expectation`, etc.) as plain
   type-hinted, docstringed Python functions — the schema the LLM cascade
   sees is derived from that (Open WebUI's pattern), not hand-duplicated
   — falling back to the existing LLM cascade only for genuinely
   open-ended questions, grounded in resume Markdown + the job posting.
   Every answer logged through step 4's event log.
8. **Real Greenhouse/Lever form-structure investigation, extending step
   1's filler (backend).** Point `detect_fields` at real, live
   Greenhouse/Lever job-posting pages (read-only — loading the page and
   running field detection is no different in kind from every scraping
   source this project already has) and confirm the hybrid grounding
   approach from step 1 generalizes to real ATS markup. **Does not
   submit anything** — this step ends at "the filler can correctly detect
   and would-be-fill a real application's fields," verified by inspecting
   the filled-but-unsubmitted state, never by clicking the real submit
   button.
9. **Closing the loop, the pieces that don't need new access (backend +
   frontend).** Interview-question surfacing when a job's status flips to
   "interviewing" — wiring two already-existing features together, no
   new access required, buildable now. **Real, hard stop on Gmail
   reply-detection specifically**: needs Google Cloud OAuth credentials
   and your explicit consent grant, which only you can set up — flagged
   here as its own separate go-ahead (see "Real tooling for closing the
   loop's reply-detection piece" above for the real package choices:
   Gmail API + `simplegmail`, `email-reply-parser`, this project's
   existing LLM cascade for classification), not assumed as part of this
   authorization. Outcome feedback (tuning the match-score threshold from
   real response data) is blocked on real submissions existing at all —
   deferred until after the submission gate below is separately crossed.

## The submission gate (separate from the authorization above)

The first real application submitted to a real company is its own
checkpoint, not included in "implement this." Once steps 2-8 above are
done and step 2's ToS findings are clean, this file will be updated with
exactly what's about to happen (which company, which job, what the
LLM-answered fields contain) and wait for explicit, in-the-moment
confirmation before that one action fires — after that first real,
confirmed submission, whether every subsequent one still requires the same
confirmation is what `SUBMIT_CONFIRMATION_POLICY` (step 3) actually
governs.

Next: steps 2-9 above (excluding the two marked hard stops — real
applicant data, Gmail OAuth setup — and excluding the submission gate,
which stays a separate checkpoint) are approved. Driven by `/loop` once
this file is committed on its own, per WORKFLOW.md rule 3.
