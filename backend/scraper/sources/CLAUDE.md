# Sources — adding or touching a source

Loaded automatically (Claude Code's nested-memory convention, verified against
code.claude.com/docs/en/memory) whenever a file under this directory is read —
supplements the root [[CLAUDE.md]], doesn't replace it. Read [[docs/ARCHITECTURE.md]]
first for the exact `Source`/`Chunk`/`Transport` contracts; this file holds the
conventions and prior-art specific to adding or editing a source.

## Verify before proposing, not after

Check `robots.txt` and licensing for any new source **before** writing it into
DESIGN.md — "seems public" is not verification. Three sources were proposed
early on the assumption they'd be low-friction and turned out not to be once
actually checked:

- **Reddit** — `robots.txt` disallows all crawling (see DESIGN.md §3).
- **LeetCode Discuss** — `robots.txt` disallows `/graphql` and `/forums`;
  Discuss is a GraphQL-driven SPA, so even a rendered browser fetch pulls data
  through a channel they've closed to crawlers.
- **Blind** — blocks even a plain `robots.txt` request with an anti-bot page.

Do not revisit these without new evidence the policy changed.

Glassdoor/LinkedIn/Indeed are similarly high-friction (login walls, anti-bot)
— deprioritize unless specifically requested and re-verified. LinkedIn,
Indeed, Glassdoor, and Naukri were all explicitly re-checked in phase 5
([[docs/phases/PHASE5.md]]) and confirmed still hostile (LinkedIn's `robots.txt` states
automated access is "strictly prohibited"; Indeed/Glassdoor disallow exactly
the job/interview paths this app wants; Naukri's edge WAF blocks non-browser
User-Agents, conflicting with this project's honest-UA policy).

Prioritize sources without explicit anti-scraping ToS friction: open job
board APIs/RSS feeds (RemoteOK, WeWorkRemotely, Arbeitnow, Himalayas,
RemoteJobs.org), and permissively-licensed curated content (GitHub question
banks — h5bp, FAQGURU) over scraping forums at all.

## Fetching

Every source goes through the `Transport` protocol
(`backend/scraper/transport.py`, [[docs/phases/PHASE4.md]]) — never add a
source-specific HTTP client outside it. `httpx` is the default (every source
so far is a plain JSON/XML/text API — none need HTML cleaning or stealth);
`scrapling` stays available as a per-source opt-in (`transport:
Literal["httpx", "scrapling"]` on `Source`) for anything that genuinely needs
stealth/JS rendering later. A source can also override politeness via
`delay_s: float = config.REQUEST_DELAY_S` on `Source` when the target asks
for it explicitly (e.g. Arbeitnow's terms say "please do not abuse").

## Chunk text

Always feed the LLM a chunk's own cleaned text, never raw HTML/XML — every
source builds its `Chunk.text` from `Page.raw` via its own
`clean_html`/field extraction (see ARCHITECTURE.md's Key contracts), not
`Page.markdown`. This is exactly why the transport can default to `httpx`
instead of Scrapling.

Real bug this caught (phase 5, FAQGURU): chunking on full question+answer
text tanked local-model extraction (1/15 chunks extracted) because
`QuestionExtract` has no answer field — the answer text added zero product
value and confused the local model. Chunking on the bare question text alone
measured 12/15 (80%) on the same real chunks. When a new source's schema
doesn't need a field, don't put that field's text in the chunk just because
it's available on the page.

## General

- Build one source end-to-end before generalizing to more sources (build
  order: [[docs/phases/PHASE1.md]]).
- Don't assume two sources share a parsing shape just because they're the
  same *kind* of platform. FAQGURU looked like it could reuse h5bp's
  `_bullet_chunks` (both GitHub-hosted markdown question banks) — a real
  fetch showed FAQGURU uses `### Question` headings with prose/code-block
  answers, not h5bp's flat bullet list, so it got its own heading-based
  parser (`_faqguru_*` prefixed) in the same file instead of a forced shared
  abstraction.
- `apply_url` should store the raw href, not a resolved redirect (avoid
  extra requests per job).
