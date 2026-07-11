# Phase 13 — Ashby, a real Workday feasibility spike, and WhatsApp job-link intake

Read [[docs/DESIGN.md]] first for the system contract; this file only holds
phase 13's step-by-step build order and rationale. See [[docs/WORKFLOW.md]]
for the recurring process this and every phase file follows.

Same workflow rules as [[docs/phases/PHASE1.md]]-[[docs/phases/PHASE12.md]].

## Why this phase exists

The user asked directly for two things: automate applications to more kinds
of jobs on different platforms, and a way to feed in job links shared over
WhatsApp. Both were discussed before any doc was written, per WORKFLOW.md
rule 1, and grounded in real, checked facts rather than assumptions before
committing to scope (rule 2):

**The ATS coverage gap is real and larger than earlier docs suggested.**
Of 2,979 companies discovered so far, only 413 (14%) resolve to Greenhouse
or Lever — the other 2,566 (86%) were *checked* and confirmed not on
either platform (`Company.last_checked_at` is set on all of them; this
isn't "never probed," it's "probed and missed"). A real gap this size is
worth a third platform.

Three candidates were spot-checked live before picking one:
- **SmartRecruiters** — clean rejection. `api.smartrecruiters.com/robots.txt`
  disallows `/` for every user-agent except `LinkedInBot`. Same shape as
  the LinkedIn/Reddit/Blind rejections (`backend/scraper/sources/CLAUDE.md`)
  — not pursued.
- **Ashby** — real, promising, and unusual. `api.ashbyhq.com/robots.txt`
  itself returns a genuine `401 Unauthorized` (confirmed via `curl -sI`,
  not just a body-text guess) — the whole subdomain requires auth by
  default — yet `GET /posting-api/job-board/{slug}` (tested live against
  `ramp`) returns clean, complete JSON with no auth at all: `title`,
  `department`, `location`, `descriptionPlain` (already plain text, no
  double-HTML-escaping to unwind, unlike Greenhouse), `jobUrl`,
  `applyUrl`. This is the same shape their own public job-board pages
  are built from — a deliberately carved-out public endpoint inside an
  otherwise-closed domain, not an accidental bypass. Picked as this
  phase's next platform.
- **Workday** — real, but inconclusive from a first check. No single
  `workday.com/robots.txt` exists to check (each customer runs on its own
  tenant subdomain, e.g. `{tenant}.wd{N}.myworkdayjobs.com`); a probe
  against one real tenant's `/robots.txt` path returned a JSON error body,
  not real robots.txt content. Likely the single biggest slice of the
  2,566 unresolved companies given its market share, but architecturally
  heavier than Greenhouse/Lever/Ashby (per-tenant naming with no obvious
  guessable convention, JS-heavy application flows). Gets its own real
  feasibility spike (step 6) before any build commitment — same discipline
  phase 9's VC-portfolio search used when four of five real candidates
  didn't pan out.

**WhatsApp intake means a receiving number, not reading an existing
channel.** Checked directly: the official WhatsApp Business Platform
(Meta's Cloud API) delivers inbound messages via webhook only for
messages sent *to a phone number you provision and verify through Meta
Business* — there is no API to subscribe to and read a channel or group
you already follow. The unofficial alternative (an automated personal
WhatsApp Web client, e.g. `whatsapp-web.js`/Baileys-style) is the same
category of thing this project just rejected for LinkedIn in
[[docs/phases/PHASE12.md]] step 4 — ToS-prohibited automation of a
personal/consumer session, with real account-ban exposure. The user chose
the compliant path: build the real forwarding number. This also means a
genuinely new architectural exception worth naming plainly: `DESIGN.md`
§4 calls this app "a local tool" that binds to localhost with no auth —
a Meta webhook needs a real, internet-reachable HTTPS URL to deliver to,
so this feature is the first thing in this codebase that requires
exposing anything to the internet at all (a tunnel like `ngrok` while the
app runs, at minimum). That tradeoff is accepted explicitly here, not
discovered by accident later.

## Build order

### Ashby

1. **Ashby API docs/ToS verification (research only, no code).** Read
   Ashby's actual public developer documentation for the Job Posting API
   (not just the live curl probe above) to confirm this is a documented,
   sanctioned integration point — company career-page embeds and ATS
   integrations are exactly what this endpoint is for — and note any
   real usage terms (rate limits, attribution requirements) found. If
   the docs contradict what the live probe suggested, stop here and
   report, the same as any other source-rejection precedent.
   **Done.** Confirmed real via the official docs
   (`developers.ashbyhq.com/docs/public-job-posting-api`, found via
   search, then fetched directly): the exact endpoint already probed
   live (`GET /posting-api/job-board/{clientname}`) is documented,
   public, and unauthenticated by design, explicitly for "if you host
   your own careers page, you can use this data to populate it" plus a
   named "Dedicated Partner Job Feeds" use case (the same category of
   thing LinkedIn/Indeed/Otta/Built In/ZipRecruiter/Levels.fyi
   integrate against, per the docs). No rate limits or attribution
   requirements documented. No restriction on automated access found —
   the opposite of the SmartRecruiters/LinkedIn/Reddit rejection
   pattern; this is a platform that wants third parties consuming this
   endpoint. Proceeding to step 2.

2. **Ashby slug resolution (backend).** Extend `resolve.py`'s `_ATS_URLS`
   with an `"ashby"` entry
   (`https://api.ashbyhq.com/posting-api/job-board/{slug}`); `resolve_company`
   already loops every entry in that dict and treats a non-200 as "not
   this platform," so no control-flow change, just a new probed URL.
   Tests: a scripted 200/404 case for the new provider, mirroring the
   existing Greenhouse/Lever test shape. Real smoke test: run
   `resolve_unresolved_companies` against the real, current 2,566
   unresolved companies and report the real new-hit count — this is the
   number that actually validates step 1's premise, not a guess.

3. **Ashby job source (backend).** `AshbyCompanySource` in
   `sources/companies.py`, mirroring `GreenhouseCompanySource`/
   `LeverCompanySource`'s shape (`seed_urls`/`next_links`/`split_items`);
   `_ashby_chunks` parses the real JSON shape confirmed above —
   `descriptionPlain` needs no `html.unescape()` step, a genuine
   simplification versus Greenhouse's chunk parser. Wire into
   `_COMPANY_SOURCE_BUILDERS` (`sources/__init__.py`). Tests: a real
   captured-shape fixture (title/department/location/descriptionPlain/
   applyUrl), a job missing `applyUrl` (skip, don't crash), a
   below-`MIN_CHUNK_CHARS` posting (skip). Real smoke test: scrape one
   real Ashby-hosted company's board for real and report how many real
   jobs landed.

4. **Ashby field-detection page preparation (backend).** Live
   investigation (a real headless browser against a real live Ashby
   `applyUrl`, same method PHASE10.md step 8 used for Greenhouse/Lever)
   of what an Ashby application form actually looks like — single page,
   multi-step, embedded iframe, whatever it really is, confirmed rather
   than assumed. Extend `providers.py`'s `prepare_application_page` with
   an `ats_provider == "ashby"` branch once the real shape is known.
   Tests mock Playwright the same way `test_autoapply_filler.py` does not
   (real local browser, real local test-form-server-style fixture built
   to match Ashby's confirmed real shape). Real smoke test: `detect_fields`
   against one real, live Ashby posting's real application page — no
   fill, no submit, matching PHASE10.md step 8's own read-only precedent.

5. **Ashby end-to-end real smoke test.** One full `plan_application` dry
   run against a real, live Ashby posting, reaching `awaiting_confirmation`
   or a real, honest failure — never confirmed, matching every prior
   phase's submission-gate discipline. `pytest`/`mypy`/`ruff` green before
   moving to Workday.

### Workday

6. **Workday feasibility spike (research only, no code — a real go/no-go
   gate).** Answer, for real, before writing any Workday-specific code:
   is there a consistent, guessable pattern from a company name to its
   real tenant subdomain (Greenhouse/Lever/Ashby's slug-guess-and-check
   pattern may simply not transfer)? Does a `/wday/cxs/{tenant}/{site}/jobs`
   POST endpoint return real public JSON without auth on a real tenant,
   confirmed live? Does `robots.txt` (checked per-tenant, since there's no
   single global one) actually allow it, on more than one real sampled
   tenant? If any of these come back genuinely infeasible or inconsistent
   across samples, stop here, document exactly what was checked and why
   it didn't pan out (the Techstars/500 Global/Index Ventures/Kleiner
   Perkins precedent, [[docs/phases/PHASE9.md]]), and skip steps 7-8
   entirely — this is a legitimate, honest outcome, not a failure to
   route around.

7. **Workday resolution + job source (backend) — only if step 6 finds a
   real, working pattern.** Same shape as steps 2-3, adapted to whatever
   real tenant-resolution and JSON shape step 6 actually found.

8. **Workday field-detection + end-to-end real smoke test — only if step
   7 lands.** Same shape as steps 4-5.

### WhatsApp job-link intake

9. **Real one-time setup path (user action, a hard stop like Gmail OAuth
   in [[docs/phases/PHASE10.md]] step 9 — documented here, not
   attempted by the build loop).** Create a Meta Business account, create
   a WhatsApp Business Platform app, provision and verify a phone number,
   and decide on a public HTTPS endpoint for the webhook (an `ngrok`/
   `localtunnel` tunnel while the app runs is the minimum viable choice
   for a tool that's otherwise local-only — a real, accepted architecture
   exception per this file's own "Why this phase exists" section, not a
   permanent hosted-service commitment). The verify-token and access
   token this produces are real secrets — `.env`-only, never committed,
   same as every other credential this project handles.

10. **WhatsApp webhook receiver (backend).** A new route handling Meta's
    verification handshake (`GET` with `hub.challenge`, echoed back only
    when `hub.verify_token` matches a real configured secret) and the
    real inbound-message `POST` payload shape (documented by Meta,
    fixture-able without any real credential). Every event gets logged;
    unrecognized/malformed payloads are rejected with a real 4xx, never
    silently dropped. Fully unit-testable with scripted payloads — no
    real Meta account needed to build or test this step.

11. **Single-URL job-intake pipeline (backend).** Every existing `Source`
    is shaped around enumerating many items from one board page
    (`seed_urls`/`split_items`) — a link shared over chat is a single,
    arbitrary URL from anywhere, a genuinely different shape. New,
    narrow path: extract URLs from an inbound message's text (a plain
    regex, not an LLM call — cheap and exact for this), fetch each one
    through the existing `PageFetcher` (robots.txt is enforced
    per-domain automatically here — a shared LinkedIn link is correctly
    blocked the same way a scheduled LinkedIn scrape would be, no new
    per-domain ToS review needed), then run the existing extraction
    cascade (`Extractor`, `JobExtract` schema) directly against that one
    page instead of a `Source`'s chunk loop. Dedupes on permalink exactly
    like every other job save path (`repo.save_job`). Tests: a message
    with one real link, multiple links, no links (no-op), a link
    `robots.txt` disallows (skipped, not a crash), a link that fails
    extraction validation (skipped, logged, not silently dropped).

12. **WhatsApp real smoke test — gated on step 9 being complete.** Send a
    real WhatsApp message containing a real job-posting link to the
    provisioned number; confirm it's received, extracted, and appears in
    the Jobs list. If step 9's setup isn't done yet when the loop reaches
    this point, stop and report exactly like every other credentialed
    hard stop in this project (Gmail OAuth, real applicant data) — never
    faked or routed around.

Next: driven by `/loop` per [[docs/WORKFLOW.md]] once the user approves
this phase; stop at step 12, or earlier at step 6/9 if either real gate
comes back negative/incomplete and nothing further in that thread can
honestly proceed.
