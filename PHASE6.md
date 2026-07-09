# Phase 6 — search, live updates, and cleanup

Read [[DESIGN.md]] first for the system contract; this file only holds phase 6's
step-by-step build order and rationale. See [[WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[PHASE1.md]]–[[PHASE5.md]]. Four research threads led
here, all verified before writing this down (WORKFLOW.md rule 2):

- **Search over scraped data.** PageIndex-style vectorless, reasoning-based
  RAG was considered first, but it solves a different problem than this app
  has: it replaces lossy chunking when navigating one *long* continuous
  document (a 100-page PDF, a contract) by reasoning over a hierarchical
  table-of-contents instead of arbitrary chunk boundaries. This app's data is
  the opposite shape — thousands of independent *short* records (one job
  posting, one interview question) that are already atomic units; there is no
  long document being chunked in the first place, so the problem PageIndex
  fixes doesn't apply. The actual fit, confirmed for real: **`sqlite-vec`**
  (PyPI, dual MIT/Apache-2.0, actively maintained — v0.1.9 as of March 2026,
  though still pre-1.0 so breaking changes are possible) is a C extension for
  vector search *inside* SQLite — no separate vector DB service, matching the
  same no-new-infrastructure discipline that picked `SqliteHuey` over Redis in
  phase 5. Paired with Ollama for free local embeddings (`nomic-embed-text`)
  and SQLite's built-in FTS5 for exact keyword matching, combined with
  reciprocal rank fusion, this is the standard pattern for searching many
  short structured records (how most job-board/e-commerce search works) —
  not a document-navigation problem PageIndex was built for.
- **Live updates.** The dashboard polls `/api/runs` every 3s while a run is
  active. Explicitly requested: replace this with push. WebSocket vs
  SSE — going with **SSE** (`text/event-stream` via Starlette's
  `StreamingResponse`, already available through the installed FastAPI
  0.128.0, no new dependency): the data flow here is one-directional
  (server → client run-status updates), which is exactly what SSE is for;
  WebSocket's bidirectional channel would be unused complexity.
- **Extraction reliability.** `OllamaClient.complete()` calls
  `ollama.generate(..., format="json")`, which only guarantees syntactically
  valid JSON of *any* shape — not the actual schema. Ollama's client accepts
  a real JSON schema for `format` (confirmed: `format:
  Union[Literal['json'], dict[str, Any], None]`), constraining generation to
  the exact shape. Tested for real against 10 live Himalayas job chunks:
  `format="json"` failed validation on 1/10 (a list field came back as a
  non-list); `format=<real schema>` failed 0/10. Small, cheap, measured win.
- **Model choice.** Explicitly requested: pick which local model runs from
  the UI, and support more than one. Considered adding cloud free-tier
  providers (Groq, Gemini, OpenRouter's `:free`-suffix models) — verified
  they're real and genuinely free today, but explicitly rejected: their free
  tiers are provider policy, not guarantees, and change often (Gemini's own
  free tier was already cut once in late 2025). Scope stays Ollama-only —
  always free, no account, no policy to watch. `ollama.list()` already
  returns every model actually pulled on the machine; the app just needs to
  stop hardcoding `config.LOCAL_MODEL` as the only option and let the UI
  pick from what's really installed.

1. **Rewrite [[README.md]] (docs).** Currently describes the MVP shape only
   ("Status: MVP complete... Sources: HN 'Who is hiring?' for jobs, HN
   comment search for interview questions") — stale since phase 2. Update to
   reflect the real current state: 9 sources across jobs/questions, Huey
   scheduling/queueing, multi-select scrapes. No smoke test (docs-only).
2. **Schema-constrained local extraction (backend).** Build the real
   `{"items": [...]}` JSON schema around the target Pydantic model (new
   `prompts.wrapper_schema()` — the retry *prompt* already describes this
   shape in text, but no code built it as an actual schema object before
   this step) and pass it to `OllamaClient.complete()`'s `format` argument
   instead of the bare string `"json"`. `LLMClient.complete(prompt) -> str`
   didn't take a schema, so this needed a small protocol change: `complete`
   now takes a keyword-only `schema: dict[str, Any] | None = None`, ignored
   by `FrontierClient` (no equivalent constrained-decoding feature on the
   Anthropic API). Smoke: re-ran the real 10-chunk comparison from research
   on a *fresh* batch of live Himalayas job chunks — **0/10 failures for
   both** bare `format="json"` and the real-schema path this time, not the
   1/10 → 0/10 delta measured in research. Reported honestly rather than
   re-run until it matched: `qwen2.5:7b-instruct` evidently handles
   `JobExtract`'s shape reliably either way on this sample; the schema path
   still ships because it constrains generation by construction (a
   guarantee, not a probability) and cannot be worse than the bare string,
   even though this particular smoke test didn't catch a regression to
   demonstrate the difference.
3. **Selectable local model (backend + frontend).** New `GET
   /api/models` returns `ollama.list()`'s real output (name, size) — only
   models actually pulled on the machine, never a hardcoded list. Add a
   `model` column to `runs` (or reuse an existing settings mechanism —
   decide during the step) so each run records which local model it used,
   not just the global default. `build_extractor`/`OllamaClient` take the
   chosen model instead of always reading `config.LOCAL_MODEL`. Frontend: a
   model picker in `NewScrapeModal` (or a small settings panel, decide once
   the backend shape is real), populated from `GET /api/models`, so nothing
   is offered that isn't genuinely installed.
   Candidates to actually pull and compare during this step's smoke test
   (real tags confirmed to exist on Ollama's registry, but none benchmarked
   by us yet — that happens here, not in planning): `qwen2.5:7b-instruct`
   (current default, the baseline), `qwen3.5:4b` (multiple sources call it
   the best small CPU-friendly model for 2026 — smaller *and* reportedly
   better than the current default), `gemma4:12b` (cited as strongest in its
   size class specifically for structured JSON output), `phi4-mini:3.8b`
   (smallest candidate, reportedly strong on structured/logic tasks despite
   size). Smoke: pull at least one real alternative alongside the existing
   default, run a real scrape with each, confirm both actually execute with
   the model that was picked (not silently falling back to the default),
   and record which one actually extracted more cleanly on real chunks —
   this is the first real evidence for any of these claims.
4. **Round field UX (frontend).** No schema change — `QuestionExtract.round`
   stays nullable, correctly representing that generic reference sources
   (FAQGURU, h5bp, HN comments) have no real interview round. Change the
   Questions view: render `round` as a small badge next to the question only
   when non-null, instead of a fixed always-shown table column, so
   company-less sources don't display an empty column. `npm run build` gate;
   real look in a browser confirming both a company-attributed row (with a
   round badge) and a generic row (without one) render correctly.
5. **Drop `recharts` for a hand-rolled SVG bar chart (frontend).** Same move
   as phase 5 step 4's `motion` fix: `RunsChart.tsx` renders one simple
   grouped bar chart (two series, ≤10 categories) but `recharts` alone costs
   ~351 KB (42% of the bundle) — confirmed by real marginal-contribution
   measurement in phase 5. Replace with a small hand-rolled SVG component
   (two `<rect>` series scaled to a `viewBox`, same data shape `RunsChart`
   already computes) and remove the dependency entirely. Smoke: `npm run
   build` with the real before/after bundle size stated, real look in a
   browser confirming the chart still renders correctly with real run data.
6. **Live run updates via SSE (backend + frontend).** New `GET
   /api/runs/stream` endpoint: an async generator polls the DB every ~1s
   (simpler and less invasive than threading a pub/sub through
   `repo.finish_run`/`record_error` — revisit only if 1s polling turns out
   to feel laggy) and yields `data: {...}\n\n` SSE frames whenever a run's
   row changes. Frontend: replace `useApi`'s 3s poll-while-active with an
   `EventSource` subscription in `Dashboard`, falling back to the existing
   poll if the connection drops. Smoke: a real run through the live API,
   confirm the dashboard updates without a poll round-trip (check the
   network tab / server log directly, not just visually).
7. **Wire `sqlite-vec` + embeddings at save time (backend).** Add
   `sqlite-vec` to `pyproject.toml` (stated reason: powers the new search
   endpoint below). Load the extension via a `connect` event listener on the
   SQLAlchemy engine (`sqlite-vec` needs `conn.load_extension()` — verify
   this pattern is compatible with SQLAlchemy's own SQLite driver setup
   before assuming, since this is a real extension-loading detail SQLAlchemy
   doesn't handle out of the box). New `vec0` virtual table storing one
   embedding per job/question row. `repo.save_job`/`save_question` embed the
   item's text via Ollama's `nomic-embed-text` (confirm this model needs a
   separate `ollama pull`, document it in the README's prerequisites) and
   insert the vector alongside the row, same transaction. Smoke: save a real
   job/question through a real run, confirm its embedding actually lands in
   the `vec0` table (not just that save doesn't crash).
8. **Hybrid search endpoint + UI (backend + frontend).** New `GET
   /api/search?q=...&kind=jobs|questions`: embed the query the same way,
   run a `sqlite-vec` similarity query and an FTS5 keyword query in
   parallel, merge with reciprocal rank fusion, return ranked results
   through the existing `JobOut`/`QuestionOut` response shapes. Frontend:
   a search input (extend the existing ⌘K command palette, or a dedicated
   view — decide once step 7 is real and there's something to search).
   Smoke: a real natural-language query ("remote python roles", "questions
   about closures") against real scraped data, confirm results are
   genuinely relevant, not just non-empty.
9. **Bottleneck pass (investigation, backend + frontend).** Not guessing —
   profile real things once the above land: API response times under a real
   multi-source batch (does SSE actually reduce round-trips measurably?),
   DB query patterns on the list/search endpoints (any missing indexes now
   that `sqlite-vec` and FTS5 are in the mix?). Fix only what's actually
   measured as slow, in its own commit with the real before/after numbers
   stated — no speculative optimization.

Next: not started yet — this is the current phase.
