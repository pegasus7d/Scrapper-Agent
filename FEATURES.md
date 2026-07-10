# Hirable — Features

A user-facing summary of what the app can actually do today. This describes
what is *true now*, verified through real smoke tests against a live app —
never a feature aspirationally described before it exists (DESIGN.md's own
docs discipline, [[docs/WORKFLOW.md]] rule 3). Written last, once every phase
listed below actually landed and passed its own real smoke test — see
[[docs/phases/]] for the build history and exact verification notes behind
every claim here.

## Job and question scraping

Nine sources across two kinds, each with its own robots.txt/licensing check
before being added ([[backend/scraper/sources/CLAUDE.md]] has the full
verify-before-adding history, including sources that were checked and
rejected — Reddit, LeetCode Discuss, Blind, LinkedIn/Indeed/Glassdoor/Naukri):

- **Jobs**: HN "Who is hiring?", RemoteOK, WeWorkRemotely, Arbeitnow,
  Himalayas, RemoteJobs.org.
- **Questions**: HN comment search, GitHub's h5bp interview-questions bank,
  FAQGURU.

Every page goes through a two-tier LLM extraction cascade: a local model
(Ollama, `qwen2.5:7b-instruct`) does the real work, validated against strict
Pydantic schemas, with the rare failed page escalated to a paid frontier
model (Claude Haiku) — so scraping thousands of pages costs approximately
nothing. Runs are scheduled and queued through Huey (`SqliteHuey`, no
separate services); manual runs, a once-a-minute periodic dispatch for
user-defined schedules, and multi-select batch runs all go through the same
task pipeline.

Live run progress streams over SSE — real-time counts (fetched, extracted,
saved, escalated), a live elapsed-time ticker, and a brief highlight flash on
any stat the instant it changes, not just a static progress bar.

## Company discovery

Six real discovery sources, each with its own real, verified page shape
(never assumed from "looks like the same platform as X") — see
[[docs/phases/PHASE8.md]] step 9 for the exact confirmation notes on each:

- **YC** (`ycombinator.com/companies`) — full scroll-driven coverage, not
  just the first page, tagged with the real YC batch (e.g. "Summer 2013").
- **Largest US companies** — Wikipedia's own revenue-ranked table, the
  closest real, public, scrape-friendly proxy for "Fortune 500," which
  paywalls its own full list.
- **a16z** — its full portfolio ships inline as a JS array on one page, no
  browser rendering needed.
- **Sequoia Capital** — a real tab-open-then-"Load More" click sequence
  reaches the full company table.
- **Founders Fund** — plain server-rendered HTML, one page, no interaction
  needed; its 10s requested crawl-delay is honored.
- **Bessemer Venture Partners (BVP)** — also plain server-rendered HTML, one
  page.

Discovered companies are automatically resolved against real ATS providers
(Greenhouse, Lever) and, once resolved, can be scraped as a real dynamic
`Source` — no hand-curated company list anywhere in this flow. Discovery can
run on-demand from the UI (pick a source, click Discover) or on a recurring
schedule (the same enable/disable/every-hours schedule mechanism jobs and
questions already use, reused rather than duplicated).

Clicking a company opens a real detail view: its metadata, its own scraped
jobs, and any interview questions tagged with its name — the payoff of
discovery, resolution, and scraping landing in one place instead of three
disconnected views.

## Application pipeline tracking

Every job carries a real status (`none` → `applied` → `interviewing` →
`offer`/`rejected`), settable from the job detail drawer, filterable
server-side from the Jobs list, and timestamped (`status_changed_at`) —
distinct from the separate starred/bookmark flag, since a job you've starred
but haven't applied to is a genuinely different state from one you have.

## Hybrid search

⌘K opens a real command palette backed by hybrid search — `sqlite-vec`
similarity search plus FTS5 keyword search, combined via reciprocal rank
fusion. A resume can be uploaded and parsed into derived search positions,
which feed directly back into the same search.

## Dashboard

Every stat card is a real navigation target, not just a display — clicking
"Jobs," "Discovered companies," etc. jumps straight to the matching filtered
view (Escalation rate stays intentionally non-interactive, since no
extraction-tier filter exists yet to send it to).

## Persistent logs

The whole app logs to both stderr and a rotating log file
(`hirable.log`, 5 MB × 3 backups, ~20 MB bound) — a real record survives
even when nobody's watching a terminal during a scheduled, unattended run.

## Prerequisites, setup, and running the app

See [[README.md]] — unchanged by this document.
