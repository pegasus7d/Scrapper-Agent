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

## Deferred — scoped but not approved to build (needs fresh confirmation)

The rest of this phase, as discussed and decided in conversation, kept
here so the scope isn't lost between sessions:

- **Autonomous submission by default, via a real, narrow, configurable
  gate** — refined from the original "fully autonomous, no per-application
  review" framing after the prior-art research above (see "Decision"
  section) surfaced real, converging evidence from OpenHands and Dify.
  `SUBMIT_CONFIRMATION_POLICY` = `always` / `risky` / `never`, defaulting
  to `risky` (pause only a genuinely high-risk `submit` — first-ever
  application to a company, or a low-confidence LLM answer). Set `never`
  to reproduce the originally-chosen fully-autonomous behavior exactly —
  this is a configurable default, not a reversal of that decision.
- **Greenhouse + Lever only, to start** — the two ATS providers this app
  already resolves companies against (`backend/scraper/resolve.py`), so
  there's real form structure to build against instead of guessing.
  External job boards that just link to arbitrary third-party apply pages
  are out of scope for this phase. If either real ATS turns out to
  paginate a single application across multiple pages (common for longer
  forms), Crawl4AI's `session_id` + `wait_for`-before-scanning pattern
  (persist one browser session across steps, wait for a real render
  signal before the field-scanner runs again) is worth mirroring — noted
  here even though Crawl4AI itself has no reusable form-aware code (see
  "Prior art checked" above), since the multi-page-session *shape* is real
  and independent of that library.
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
  above a real threshold, not on every match. Pipeline structure informed
  by the prior-art research above: a real gate step (match-score →
  threshold check → proceed/skip), not an implicit if-statement buried in
  a bigger function — mirrors Dify's if-else-node-plus-shared-variable-pool
  pattern (one namespaced context object — `job_id`, `match_score`,
  `applicant_profile.*`, `llm_answers.*` — threaded through every step) at
  the *pattern* level, not by adopting Dify itself. Langflow's lightweight
  string-tag idea (`produces: list[str]` / `consumes: list[str]` on each
  step) is a cheap way to catch a wired-wrong pipeline at construction
  time without building a real graph engine — a real graph executor
  (Langflow's own honest verdict on itself) would be overkill for this
  phase's fixed, known step sequence.
- **Form-filler priority**: structured applicant-profile fields answer
  factual questions first; the existing LLM cascade (local → frontier
  escalation, same pattern as job/question extraction) only handles
  genuinely open-ended questions, grounded in resume Markdown + the
  specific job posting. Every answer logged per-application for later
  audit. Concrete tool-definition pattern from Open WebUI: each
  structured-field lookup (`get_phone`, `get_salary_expectation`, etc.) is
  a plain Python function with type hints and a docstring — the schema the
  LLM cascade sees is *derived* from that (mirroring
  `convert_function_to_pydantic_model()`), not hand-duplicated — and kept
  as a real callable **Tool** the cascade decides to invoke, cleanly
  separate from any pre/post-processing step (Open WebUI's Tools-vs-
  Functions split) like PII redaction before logging an answer.
- **Safety controls**, treated as near-mandatory given autonomous
  operation, not optional: a daily/per-run application cap (same pattern
  `MAX_ESCALATIONS_PER_RUN` already uses), a real kill switch to pause all
  auto-apply activity immediately, a company blocklist/allowlist,
  duplicate-application prevention across discovery sources, pacing/
  time-of-day spread instead of bursty submission, plus the resolved
  `SUBMIT_CONFIRMATION_POLICY` gate above (its own bullet — a `risk` tag
  on the `submit` action specifically, fail-safe-to-HIGH on any classifier
  error). OpenHands' dual
  hard-cap pattern (`max_iteration_per_run` + `max_budget_per_run`) maps
  directly onto "max applications per run" + "max LLM spend per run," and
  its separate `StuckDetector` (repetition/loop detection) is a real,
  cheap addition against a malformed ATS form causing a runaway retry
  loop — distinct from the application-count cap, which wouldn't catch
  that failure mode on its own.
- **Trust-building**: a per-application audit record (what was actually
  submitted, any LLM-generated answers, a snapshot of the confirmation
  page) and a dry-run mode (simulate N matches, show what would have been
  submitted, without a permanent per-application review gate). Concrete
  structure from OpenHands: an append-only, timestamped, parent/child-
  linked event log (propose → execute → observe, one real row per action)
  rather than free-text logging — gives a genuine per-application replay
  ("what did it actually try, in what order, what came back") instead of
  just a final outcome summary, and is the same shape this project's own
  `Run` row already uses for scrape observability (`pages_fetched`,
  `items_saved`, `errors`) — a natural extension, not a new concept.
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
