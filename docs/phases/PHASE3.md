# Phase 3 — plugin architecture + more platforms

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 3's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]/[[docs/phases/PHASE2.md]]. Two things motivated this phase:
`sources.py`'s flat if/elif dispatch across three functions would hit the
300-line cap again the moment a 4th or 5th platform landed (the exact failure
mode [[docs/phases/PHASE2.md]] step 8 just hit for `routes.py`/`repo.py`) — so formalize the
plugin shape *before* adding more platforms, not after. Second, the
interview-questions source is still weak (HN comment search returns mostly
meta-discussion, few real questions); rather than scrape another forum, ingest
curated, permissively-licensed content instead.

**Sources investigated and rejected before writing this file** (so nobody
re-proposes them): **LeetCode Discuss** — `leetcode.com/robots.txt` disallows
`/graphql` and `/forums`; Discuss is a client-rendered SPA that fetches
everything through GraphQL, so even a stealth/browser fetch would pull data
through a channel they've explicitly closed to crawlers. **Blind** — returns an
anti-bot block page even for a plain `robots.txt` request. Both join Reddit
(DESIGN.md §3, disallows all crawling) on the "do not revisit" list.

1. **Formalize the `Source` protocol + registry (backend, no behavior change).**
   Convert `scraper/sources.py` into a `scraper/sources/` package: a `Source`
   Protocol (`seed_urls`, `next_links`, `split_items` — no fetching, that stays
   in `fetcher.py`), one file per existing platform (`hn.py`, `remoteok.py`),
   and a `SOURCES` registry dict that the package's `__init__.py` dispatches
   through. `pipeline.py`'s calls (`sources.seed_urls(...)` etc.) do not change.
   Mirror the existing tests into `tests/sources/test_hn.py` etc. Smoke: full
   test suite passes unchanged (same proof pattern as the `repo/` package split)
   plus one real HN scrape to confirm the registry dispatch actually fetches.
2. **WeWorkRemotely job source.** Public RSS feed per category (e.g.
   `weworkremotely.com/categories/remote-programming-jobs.rss`) —
   `robots.txt` is `Allow: /` for `User-agent: *` with only account/admin paths
   disallowed. One `<item>` = one `Chunk`, `url` = the item's `<link>`.
3. **Arbeitnow job source.** Public JSON API (`arbeitnow.com/api/job-board-api`),
   `robots.txt` has no disallow rules at all. Structured fields (position,
   company, location, description) still routed through the same LLM
   extraction path as every other source, same reasoning as RemoteOK
   ([[docs/phases/PHASE2.md]] step 7).
4. **GitHub curated question-bank source.** Ingests
   `h5bp/Front-end-Developer-Interview-Questions` (MIT licensed, 60k+ stars) —
   flat markdown bullet lists of real questions, no answers, no company
   attribution — via `raw.githubusercontent.com`, which has no `robots.txt` at
   all (it's GitHub's CDN, built for programmatic access, same category as
   their REST API). One markdown file = one page; each top-level bullet
   (including its sub-bullets) = one `Chunk`. Requires:
   - `QuestionExtract.company` and `interview_questions.company` become
     nullable (DESIGN.md §2) — this source is genuinely companyless, not a gap
     in the data. `question_hash` normalizes null company to `""` before hashing.
   - The questions relevance-gate prompt ([[docs/phases/PHASE2.md]] step 2) relaxes the "a
     specific company must be named" requirement to "a company is named, OR
     this is a well-known generic technical/behavioral question" — the
     company-naming rule was never really what filtered HN's junk (the
     rejected examples *did* name a company); the "concretely stated, actually
     asked" criteria did the real work, so relaxing this one clause doesn't
     reopen that hole.
   - Smoke: real fetch + local-model extraction of a few bullets from the live
     file, confirm `company: null` rows save correctly and dedupe against
     re-runs the same way company-attributed ones do.

**Phase 3 (steps 1–4) is complete** — every step validated and smoke-tested.
Two real bugs surfaced by the required smoke tests, each fixed in its own
commit: `RobotFileParser.read()` sends urllib's generic default User-Agent
internally, which WeWorkRemotely 403s (silently read as "disallow
everything" even though the real robots.txt is open) — fixed by fetching
robots.txt with our own honest UA. And `normalize_url()` stripped URL
fragments, which silently collapsed every GitHub question-bank entry in a
file onto one URL after the first — fixed by no longer stripping fragments.

**CLAUDE.md correction alongside step 1:** the original "Sources" section
listed LeetCode Discuss, Blind, and "relevant subreddits" as example
*low*-friction sources — every one of the three turned out to be high-friction
or fully disallowed once actually checked. Fixed to reflect what's been
verified, not what seemed plausible at the start.

Next: [[docs/phases/PHASE4.md]].
