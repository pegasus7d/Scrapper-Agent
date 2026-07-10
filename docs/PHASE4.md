# Phase 4 — architecture for scale, not just more sources

Read [[docs/DESIGN.md]] first for the system contract; this file only holds phase 4's
step-by-step build order and rationale. See [[docs/WORKFLOW.md]] for the recurring
process this and every phase file follows.

Same workflow rules as [[docs/PHASE1.md]]/[[docs/PHASE2.md]]/[[docs/PHASE3.md]]. Phase 3 added three
sources on top of the plugin architecture from its own step 1; phase 4 is
about the two axes that get more valuable the more sources exist, done now
while there are only 6 (cheap) rather than retrofitted at 15 (expensive) —
plus one piece of UI polish that doesn't depend on either.

1. **Split `sources/` by domain, not just by platform (backend, no behavior
   change).** Today `sources/` separates by *platform* (one file per site) but
   not by *domain* — `hn.py` even mixes `HNJobs` and `HNInterviews` in one
   file, and the registry is one flat dict distinguished only by reading each
   entry's `.kind`. Split into `sources/jobs/` and `sources/questions/`
   subpackages (DESIGN.md §3), each with its own small registry; the top-level
   `sources/__init__.py` merges both into one `SOURCES` dict so
   `pipeline.py`'s calls (`sources.seed_urls(...)`, `sources.Chunk`, etc.)
   don't change at all — same re-export-flat pattern as the `repo/` package
   split ([[docs/PHASE2.md]] step 8). `_base.py` (`Chunk`, `clean_html`,
   `MIN_CHUNK_CHARS`) stays shared at the top level; the one-line
   `_HN_PERMALINK` format string used by both HN sources is small enough to
   just duplicate rather than share (CLAUDE.md: "three lines is better than a
   premature abstraction"). Smoke: full test suite passes unchanged, plus one
   real HN jobs scrape and one real HN interview-questions scrape to confirm
   both halves of the split still dispatch correctly.
2. **Extract a `Transport` protocol from `fetcher.py` (backend).** Confirmed
   before writing this: no source's `split_items` reads `Page.markdown` —
   every one of the 6 sources so far is a plain JSON/XML/plain-text API, so
   Scrapling's HTML-cleaning and stealth-fetch capability (the whole reason
   it was chosen originally, per CLAUDE.md's Stack section) sit completely
   unused. Define `Transport` (`get(url, *, timeout, headers) ->
   TransportResponse`) in `transport.py` (DESIGN.md §3); `PageFetcher` keeps
   every bit of its policy (robots.txt, retry/backoff, honest UA) unchanged
   and just delegates the request to whichever transport it's given. Add
   `HttpxTransport` (promote the existing `httpx` dev dependency to a regular
   one — it's already pinned, just needs to stop being test-only) as the new
   default; keep `ScraplingTransport` as a real, still-tested alternative, not
   removed — available the moment a source genuinely needs stealth/JS
   rendering. Each `Source` declares `transport: Literal["httpx", "scrapling"]
   = "httpx"`; the code that builds a run's `PageFetcher` reads the source's
   choice. Existing `test_fetcher.py` fixtures move from monkeypatching
   `ScraplingFetcher.get` directly to faking the `Transport` protocol — less
   coupled to Scrapling's internals, more coupled to the actual contract.
   Smoke: one real scrape via `HttpxTransport` (any current source) and one
   real scrape forced onto `ScraplingTransport` (prove it still genuinely
   works, even though nothing defaults to it).
3. **Per-source politeness override, riding on step 2's metadata (backend).**
   `REQUEST_DELAY_S`/`FETCH_RETRIES` are global today; Arbeitnow's own API
   terms literally say "please do not abuse," while GitHub's CDN can take
   more load than a small job board. Add `delay_s: float =
   config.REQUEST_DELAY_S` to `Source` (DESIGN.md §3) — most sources don't
   override it; the pipeline's `sleep(...)` call between pages reads the
   run's source's `delay_s` instead of the global constant directly. Smoke:
   not needed on its own (no new network path) — covered by step 2's smoke
   tests re-running with a source that sets a non-default `delay_s`.
4. **Multi-select sources in the "New scrape" modal (frontend only).** No
   backend change — the existing one-run-at-a-time invariant already fits
   this. `NewScrapeModal` becomes checkboxes; on submit, queue the selected
   sources and run them one at a time (start → poll `/api/runs/{id}` to a
   terminal status → start the next), matching DESIGN.md §6's description.
   `npm run build` gate as usual; no real backend smoke test needed since
   nothing server-side changes, but do one real manual multi-source run
   through the UI before calling this step done.

**Phase 4 (steps 1–4) is complete** — every step validated and smoke-tested.
No bugs surfaced this phase; every smoke test passed clean on the first try,
including a real two-source queue run (`github-questions` then
`hn-interviews`) through the live API for step 4, driven through the exact
start → poll → start-next sequence the UI performs.

Next: no phase 5 yet — propose next steps and wait to be asked, per
[[docs/WORKFLOW.md]] rule 7.
