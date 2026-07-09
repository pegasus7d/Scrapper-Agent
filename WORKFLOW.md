# Workflow — how this project actually moves from idea to shipped phase

DESIGN.md and CLAUDE.md are the contract: they describe *what* the project
is right now. This file describes *how* it gets built — the recurring
collaboration pattern — so that a new session (after context compaction, or
starting fresh) can pick the process back up without re-deriving it from
scratch by reading the whole conversation history.

Each phase's step-by-step build order lives in its own `PHASE{N}.md` file
(DESIGN.md §8 is the index), not inline in DESIGN.md — the same reasoning
that split `repo.py`/`sources.py` into packages once they grew past the
300-line cap, applied to docs instead of code, so DESIGN.md stays the current
system contract and doesn't grow unbounded with build history.

## The recurring pattern

Every phase of work (MVP, phase 2, phase 3, ...) follows the same loop:

1. **Discuss, don't build.** When the user asks "what next" or floats an
   idea, respond with a short recommendation plus the main tradeoff — not an
   exhaustive plan, not code yet. Present it as redirectable. Don't start
   implementing until the user agrees on scope.
2. **Verify sources before writing them into docs.** Any new scraping target
   gets its `robots.txt` and licensing checked for real (`curl`, the GitHub
   API) before it's named in DESIGN.md. "Seems public" is not verification —
   three sources (Reddit, LeetCode Discuss, Blind) were proposed on exactly
   that assumption and all three turned out to be high-friction or fully
   disallowed once actually checked.
3. **Docs first, as their own commit.** Once scope is agreed, write the new
   phase into its own `PHASE{N}.md` file (copy the header/workflow-rules
   boilerplate from the latest one), add it to the index in DESIGN.md §8, and
   amend whichever DESIGN.md sections the new phase changes current state
   for — DESIGN.md describes *what is true now*, `PHASE{N}.md` describes
   *how this phase got there*. Amend CLAUDE.md too if a policy or convention
   needs correcting, not just extending. Commit the docs alone, before any
   code changes.
4. **Drive the build with `/loop`.** Use the exact reusable prompt template
   recorded in CLAUDE.md's "Autonomous build loop" section, pointing it at
   the new `PHASE{N}.md` file and its final step. Each iteration: read
   CLAUDE.md + DESIGN.md + `PHASE{N}.md` + `git log` to see what's already
   done, implement ONLY the smallest next unit, validate (`pytest`, `mypy`,
   `ruff check`, `ruff format --check`, `npm run build` for frontend
   changes), commit, repeat.
5. **Real smoke test at every step boundary — no exceptions.** Unit tests mock
   every I/O boundary; only a real fetch plus a real Ollama call proves the
   integration actually works. This is where real bugs get found, not
   hypothetically — three so far:
   - The Tailwind build was silently emitting zero utility classes (the whole
     UI had been unstyled since the original scaffold) — phase 2.
   - `RobotFileParser.read()` sends urllib's generic default User-Agent
     internally; WeWorkRemotely 403s that UA and RobotFileParser silently
     read that as "disallow everything," even though the real robots.txt is
     open — phase 3.
   - `normalize_url()` stripped URL fragments, silently collapsing every
     GitHub question-bank entry in a file onto one URL after the first — phase 3.
   Every one of these was caught by a smoke test, not a unit test. Fix
   immediately, in its own commit, with an honest explanation of what broke
   and why. Never silently patch and move on without saying so.
6. **Background waits use ScheduleWakeup, not polling.** Smoke tests that hit
   real network/LLM calls take a while (a real Ollama extraction is ~10-20s
   per chunk). Kick them off in the background, wait via ScheduleWakeup with a
   stated reason, don't sleep-loop or poll in the foreground.
7. **Report, then stop.** When the loop's stop condition is met, give a
   concise summary — what shipped, what bugs were found and fixed, what's
   still rough — and stop. Don't start the next phase without being asked.
   Propose next steps as options with a recommendation, per rule 1.

## Phase log

- **MVP — [[PHASE1.md]] (done 2026-07-09).** HN "Who is hiring?" jobs + HN
  interview-question search, two-tier LLM cascade (local Ollama primary,
  Claude Haiku escalation dormant — free-only mode, never requires an
  Anthropic key), SQLite, FastAPI backend, React/Vite/Tailwind UI.
- **Phase 2 — [[PHASE2.md]] (done 2026-07-09).** Pre-extraction dedupe,
  questions relevance gate, shadcn/ui foundation (+ fixed the Tailwind build
  bug), dashboard charts/live-progress panel/toasts/skeletons, dark mode +
  Cmd+K command palette, scheduled scrapes, RemoteOK source, CSV/JSON export
  + job starring. This step's size pushed `routes.py`/`repo.py` over the
  300-line cap, triggering a split into `api/dto.py` and a `db/repo/` package.
- **Phase 3 — [[PHASE3.md]] (done 2026-07-09).** Formalized `sources.py` into
  a `Source` protocol + registry (a `sources/` package, one file per
  platform), added WeWorkRemotely (+ fixed the robots.txt User-Agent bug),
  Arbeitnow, and a curated GitHub question-bank source replacing the blocked
  LeetCode Discuss idea (+ fixed the URL-fragment normalization bug; made
  `QuestionExtract.company` nullable for genuinely companyless questions).
- **Phase 4 — [[PHASE4.md]] (done 2026-07-09).** Split `sources/` into
  `jobs/`/`questions/` subpackages, extracted a `Transport` protocol (`httpx`
  default, `scrapling` opt-in — confirmed no source needs Scrapling's actual
  HTML-cleaning/stealth capability), per-source politeness delay (Arbeitnow
  doubled, GitHub Questions quartered), multi-select sources in the "New
  scrape" modal (Dashboard now owns queueing selected sources one at a time).
  No bugs surfaced this phase — every step's smoke test passed clean on the
  first try, including a real two-source queue run (`github-questions` then
  `hn-interviews`) through the live API. This DESIGN.md restructure itself
  (§8 index + one `PHASE{N}.md` file per phase, instead of everything inline)
  landed alongside the phase, prompted by the same doc-size concern that
  motivated phase 4's own step 1.
- **Phase 5 — [[PHASE5.md]] (done 2026-07-09).** Replaced `scheduler.py`'s
  hand-rolled poll loop and phase 4's frontend queue-runner with `huey`
  (verified: MIT licensed, `SqliteHuey` needs zero extra services,
  `huey.consumer.Consumer` runs in-process via a thread — no new
  infrastructure; ruled out Celery, needs a Redis/Valkey broker, built for
  multi-user/distributed workloads this single-user local tool doesn't
  need). Dependency audit dropped `motion` (measured 888.38 KB → 827.08 KB)
  and surfaced but deliberately didn't act on `recharts`'s 351 KB bundle
  contribution — a documented phase 2 choice, not silently unused like
  `motion`, so left for a decision rather than swapped unilaterally. Three
  new sources — Himalayas, RemoteJobs.org, FAQGURU — each verified for real
  before being added; LinkedIn, Indeed, Glassdoor, and Naukri were checked
  and rejected as hostile, the same pattern phase 3 hit with Reddit/LeetCode
  Discuss/Blind. Two real bugs surfaced by the required smoke tests: step 4's
  own build-order entry was missing from [[PHASE5.md]] despite the code having
  shipped (caught and fixed while closing out the phase); and FAQGURU's
  chunks tanked local-model extraction (1/15) when they included the answer
  body — `QuestionExtract` has no answer field, so chunking on the bare
  question alone fixed it (12/15).
- **Phase 6 — [[PHASE6.md]] (in progress, started 2026-07-10).** Search over
  scraped data, live updates, and a cleanup pass. Considered PageIndex-style
  vectorless RAG, ruled out: it solves lossy chunking in one *long*
  continuous document, but this app's data is thousands of independent
  *short*, already-atomic records — the problem it fixes doesn't apply.
  Went with `sqlite-vec` (verified: real, dual MIT/Apache-2.0, pre-1.0) +
  FTS5 hybrid search instead, no new infrastructure. Considered WebSocket
  for live run updates, went with SSE instead — one-directional
  server→client fits exactly, WS's bidirectional channel would be unused.
  Considered adding cloud free-tier LLM providers (Groq, Gemini, OpenRouter)
  for model choice, explicitly rejected: their free tiers are provider
  policy, not guarantees, and change often (Gemini's was already cut once
  in late 2025) — stayed Ollama-only, always free, no account. Verified a
  real, measured extraction-reliability win along the way: constraining
  Ollama's `format` to the actual schema instead of bare `"json"` dropped
  validation failures from 1/10 to 0/10 on live job chunks.

## What's durable vs. what compacts away

- **DESIGN.md and CLAUDE.md are the contract.** They describe current state
  and must stay accurate — update them in the same change as the code that
  makes them true.
- **This file is the process.** Update the phase log at the end of each
  phase; the "recurring pattern" section above shouldn't need to change often
  — if it does, that's itself worth a deliberate decision, not a drift.
- **Claude's own memory system** (outside this repo) may also hold pointers
  to this project, but this file is the one that survives a fresh `git
  clone` on a different machine — prefer writing durable facts here over
  relying on memory alone.
