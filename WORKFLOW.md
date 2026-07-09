# Workflow — how this project actually moves from idea to shipped phase

DESIGN.md and CLAUDE.md are the contract: they describe *what* the project
is right now. This file describes *how* it gets built — the recurring
collaboration pattern — so that a new session (after context compaction, or
starting fresh) can pick the process back up without re-deriving it from
scratch by reading the whole conversation history.

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
   phase into DESIGN.md as a new numbered build-order section (§8 = MVP, §9 =
   phase 2, §10 = phase 3, next one is §11, ...). Amend CLAUDE.md too if a
   policy or convention needs correcting, not just extending. Commit the docs
   alone, before any code changes.
4. **Drive the build with `/loop`.** Use the exact reusable prompt template
   recorded in CLAUDE.md's "Autonomous build loop" section, swapping in the
   new section number and its final step. Each iteration: read CLAUDE.md +
   DESIGN.md + `git log` to see what's already done, implement ONLY the
   smallest next unit, validate (`pytest`, `mypy`, `ruff check`,
   `ruff format --check`, `npm run build` for frontend changes), commit, repeat.
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

- **MVP — DESIGN.md §8 (done 2026-07-09).** HN "Who is hiring?" jobs + HN
  interview-question search, two-tier LLM cascade (local Ollama primary,
  Claude Haiku escalation dormant — free-only mode, never requires an
  Anthropic key), SQLite, FastAPI backend, React/Vite/Tailwind UI.
- **Phase 2 — DESIGN.md §9 (done 2026-07-09).** Pre-extraction dedupe,
  questions relevance gate, shadcn/ui foundation (+ fixed the Tailwind build
  bug), dashboard charts/live-progress panel/toasts/skeletons, dark mode +
  Cmd+K command palette, scheduled scrapes, RemoteOK source, CSV/JSON export
  + job starring. This step's size pushed `routes.py`/`repo.py` over the
  300-line cap, triggering a split into `api/dto.py` and a `db/repo/` package.
- **Phase 3 — DESIGN.md §10 (done 2026-07-09).** Formalized `sources.py` into
  a `Source` protocol + registry (a `sources/` package, one file per
  platform), added WeWorkRemotely (+ fixed the robots.txt User-Agent bug),
  Arbeitnow, and a curated GitHub question-bank source replacing the blocked
  LeetCode Discuss idea (+ fixed the URL-fragment normalization bug; made
  `QuestionExtract.company` nullable for genuinely companyless questions).

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
