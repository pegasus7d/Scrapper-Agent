# Phase 2 — polish & usefulness

Read `DESIGN.md` first for the system contract; this file only holds phase 2's
step-by-step build order and rationale. See `WORKFLOW.md` for the recurring
process this and every phase file follows.

Same workflow rules as `PHASE1.md`: one step at a time, small commits, all checks
green (now including `npm run build` for frontend changes), real smoke test at each
step boundary before moving on.

1. **Pre-extraction dedupe (backend).** The pipeline currently re-extracts every
   chunk and discards duplicates only at save time — a repeat HN run burns ~80
   minutes of LLM time to save nothing. Skip chunks whose normalized permalink is
   already stored (repo helper + pipeline check, counted as duplicates on the run)
   + tests. Smoke: re-run the HN jobs scrape; it must finish in seconds with
   `items_duplicate` > 0 and zero LLM calls for known chunks.
2. **Questions relevance gate (backend).** The local model saves junk ("exit
   interview questions for middle school"). Tighten the questions prompt: only
   concrete questions asked in a real tech interview, company must be named in
   the text, else return the empty list + tests pinning the prompt contract.
   Smoke: hn-interviews run; junk comments yield empty lists, not garbage rows.
3. **shadcn/ui foundation (frontend).** Vendor the primitives (button, dialog,
   sheet, table, select, badge, input, skeleton), add sonner, and swap the
   existing views to them at visual parity — no redesign in this step.
4. **Dashboard upgrade (frontend).** recharts (items saved per run, escalation
   trend), live progress panel for the active run (pages/saved/errors ticking),
   skeleton loaders, real empty states, toasts for run started/finished/failed.
5. **Delight pass (frontend).** motion transitions (drawer/dialog, stat count-up,
   running-badge pulse), ⌘K command palette (switch views, search jobs), dark
   mode toggle.
6. **Scheduled scrapes.** `schedules` table (kind, source, every_hours, enabled,
   last_run_at), a background thread in the app factory that starts due runs
   (skipped while another run is active), API endpoints + a small UI toggle on
   the dashboard + tests with a fake clock.
7. **Third source: RemoteOK** jobs via its public JSON API (`remoteok.com/api`,
   robots-friendly, attribution required — link back to the posting) — proves
   adding a source is still just seeds + chunking.
8. **Export & bookmarks.** CSV/JSON export endpoints for jobs/questions with the
   current filters applied + download buttons; a starred flag on jobs with a
   "starred only" filter.

**Phase 2 (steps 1–8) is complete** — every step validated and smoke-tested.
This step also triggered a size-driven refactor: `routes.py` and `repo.py` both
crossed the 300-line cap, so `routes.py`'s Pydantic models moved to `api/dto.py`
and `repo.py` became a `repo/` package (`_writes.py`, `_queries.py`,
`_schedules.py`, re-exported flat via `__init__.py` — no call site changed).

Next: `PHASE3.md`.
