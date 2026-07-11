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
   **Done.** `_ATS_URLS` gained `"ashby": "https://api.ashbyhq.com/
   posting-api/job-board/{slug}"` as a third entry, checked last so the
   existing Greenhouse-then-Lever hit order/tests are unchanged;
   `resolve_company`'s existing loop needed zero control-flow changes.
   Two new tests (`test_resolve_company_falls_through_to_ashby`,
   `test_resolve_company_returns_none_on_triple_404`, replacing the old
   double-404 test). `pytest` (485 passed) / `mypy` / `ruff check` /
   `ruff format --check` all green.

   Real smoke test — run against a scratch copy of `hirable.db` first
   (`cp hirable.db /tmp/scratch_phase13_resolve_check.db`, same
   real-DB-safety discipline CLAUDE.md's migration rule established,
   applied here too since this is a large, real mutation across 2,566
   rows): `resolve_unresolved_companies` took **5,137.1s (~86 minutes)**
   real wall time — sequential, no concurrency, no artificial delay, one
   HTTP round-trip at a time — and reported `checked=2566 resolved=340`.
   Broken down by provider in the scratch DB: **338 newly resolved to
   Ashby**, 2 newly resolved to Greenhouse (a real board/slug change
   since the last check, not an Ashby effect). Coverage nearly doubled:
   **413/2,979 (14%) before → 753/2,979 (25%) after**, purely from
   adding one platform. One transient real error surfaced and handled
   exactly as designed: a single "connection reset by peer" against
   Greenhouse for "Quidsi (fka Diapers.com)," caught by the existing
   `except TransportError: continue` and correctly treated as a miss,
   not a crash. A real, honest mid-run finding: the Ashby-hit rate
   wasn't uniform — it flatlined at 315 for 813 companies in a row
   partway through (large, older enterprises — NRG Energy, Palo Alto
   Networks, Acadia Healthcare, Walt Disney Company — plausibly not on
   any startup-favored ATS), then resumed. Verified this wasn't
   breakage (only the one warning above in the entire run, and `lsof`
   showed a healthy live connection throughout) before concluding it was
   real company-mix variance, not a bug — the same "flatlined but still
   producing new resolutions before the run ended" pattern that,
   unverified, would have looked exactly like silent rate-limiting.

   **The 340 real resolutions above are not yet in the real `hirable.db`**
   — they exist only in the scratch copy. Copying them back (a
   name-matched, per-row `mark_company_checked` replay, chosen over
   re-running the full ~86-minute probe against `hirable.db` directly to
   avoid ~7,700 redundant real requests against Ashby/Greenhouse/Lever)
   was flagged by the permission system as a write to a shared/production
   resource needing explicit authorization, since it wasn't something
   the user had specifically cleared — correctly stopped rather than
   worked around. Asked the user directly which they'd prefer (the
   targeted merge, or a full re-run against `hirable.db` itself);
   decision pending. This step's code (the resolver change + tests) is
   complete and committed regardless — only persisting the real
   resolution data to the live database is on hold.

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
   **Done.** Landed close to plan, with one field-naming correction:
   `jobUrl` is this source's own chunk URL (Greenhouse/Lever's
   `absolute_url`/`hostedUrl` equivalent), not `applyUrl` — every real
   `applyUrl` sample seen is exactly `{jobUrl}/application`, the same
   deterministic-suffix relationship Lever's `{hostedUrl}/apply` already
   has, so it's derived in step 4 rather than stored separately. Ashby's
   `location` field is already a plain string (unlike Greenhouse's
   nested `{"name": ...}`), and `descriptionPlain` needs no
   `html.unescape()` — a genuine simplification versus both existing
   parsers. 5 new tests in `tests/sources/jobs/test_companies.py`,
   mirroring the Greenhouse/Lever shape exactly (seed URL, real chunk
   build, skip-short-and-urlless, empty next_links, malformed-payload
   ValueError).

   **A real bug, caught by the smoke test exactly as CLAUDE.md intends:**
   the first real run raised `RobotsDisallowed` — `api.ashbyhq.com/
   robots.txt` returns a genuine `401`, and the existing fetcher policy
   (written for WeWorkRemotely's real `403`-to-honest-UA case,
   [[docs/phases/PHASE3.md]]) treated any `401`/`403` on robots.txt as
   "respect this as a full disallow." That's wrong for this specific,
   independently-verified case: a `403` is a deliberate "we see you and
   reject you" signal (WeWorkRemotely's real behavior); a `401` only
   means "this resource requires credentials," which says nothing about
   whether some *other* path is meant to be public — and step 1 already
   confirmed via Ashby's own developer docs that this exact API path is
   a deliberate public carve-out. Fixed by splitting the two codes in
   `fetcher.py`'s `_fetch_robots_lines`: `403` still means full disallow
   (unchanged, WeWorkRemotely's real case stays correct), `401` is now
   treated the same as a missing robots.txt (unrestricted) — a shared-
   module change, not a source-specific hack, so it's covered by a new
   shared test (`test_robots_401_treated_as_allow_all`) alongside the
   existing `403` test, both passing. Re-running the real smoke test
   after the fix: **128 real chunks from Ramp's live Ashby board**
   (`https://jobs.ashbyhq.com/ramp/...`), first chunk a real "Technical
   Consultant, Mid-Market" posting with real description text. `pytest`
   (491 passed, +6 counting the fetcher test) / `mypy` / `ruff check` /
   `ruff format --check` all green.

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
   **Done.** Real shape confirmed live against Ramp's actual application
   page (`https://jobs.ashbyhq.com/ramp/.../application`): Lever's shape,
   not Greenhouse's — a distinct URL, every field already visible on
   load, no button click needed, and `{jobUrl}/application` matches every
   real `applyUrl` sample seen exactly, so `providers.py`'s `"ashby"`
   branch is a one-line `page.goto`.

   **A second real bug, in the shared filler, not just this provider:**
   the live page raised a 30-second `Locator.aria_snapshot: Timeout`
   inside `detect_fields` itself — Ashby's application page has no
   `<form>` element at all (a React app rendering inputs directly in the
   page body), so `page.locator("form")` never matched anything. Fixed
   in `filler.py`: `detect_fields` now snapshots `page.locator("body")`
   instead — a strict superset of whatever a real `<form>` would
   contain, confirmed backward-compatible by re-running every existing
   Greenhouse/Lever-shaped `test_autoapply_filler.py` test unchanged (all
   9 still pass). Added `ashby-like` routes to `test_form_server.py`
   (a job page + a no-`<form>` application page, reproducing the exact
   real shape that broke) plus a dedicated
   `test_detect_fields_works_on_a_page_with_no_form_element` test.

   **A real, honest limitation found and not fixed here:** re-running
   the real `detect_fields()` against Ramp's live page found 7 native
   fields correctly (`_systemfield_name`/`_systemfield_email` as
   Legal Name/Email, a UUID-`id` phone field, `_systemfield_resume` as a
   file upload, a UUID-`id` LinkedIn text field, one free-text textarea
   question, and the SMS-consent radio group) — but Ashby's *custom*
   Yes/No screening questions ("Do you have 2+ years in technical
   consulting...", "Have you worked with ERP systems...") render as real
   `<button>` elements, not native `<input type="radio">`, and the
   location field is a custom combobox, not a `<select>` — none of the
   three are visible to `detect_fields`'s DOM query
   (`input:visible, select:visible, textarea:visible`) at all. This is a
   genuine capability gap (recognizing ARIA button-toggle groups and
   comboboxes as fillable fields), not a bug in what step 4 scoped, and
   is not fixed here — an Ashby application today will plan correctly
   against every native field and silently have no data for these custom
   questions, exactly the same "unanswered, not fabricated" honesty the
   answer-tool system already guarantees for any field with no matching
   data (PHASE10.md step 7). 4 new tests (provider navigation + the
   no-form `detect_fields` test). `pytest` (493 passed, +2 net after the
   test-file real-shape correction) / `mypy` / `ruff check` /
   `ruff format --check` all green.

5. **Ashby end-to-end real smoke test.** One full `plan_application` dry
   run against a real, live Ashby posting, reaching `awaiting_confirmation`
   or a real, honest failure — never confirmed, matching every prior
   phase's submission-gate discipline. `pytest`/`mypy`/`ruff` green before
   moving to Workday.
   **Done.** First real run surfaced a third real bug, caught by this
   step's own smoke test exactly as intended: `plan_application` finished
   in 1.4s and reported `status=failed, error="no fillable fields
   detected"` — far too fast for a real Playwright run, and wrong, since
   step 4 had already confirmed 7 real fields exist. Root cause: Ashby's
   application page is client-rendered (React), so its fields aren't in
   the DOM yet when `wait_until="domcontentloaded"` fires — `detect_fields`
   ran against a still-empty page. Fixed in `providers.py`'s `"ashby"`
   branch: after navigating, wait on the same selector `detect_fields`
   itself queries (`page.wait_for_selector(FIELD_SELECTOR, timeout=10000)`)
   before returning — a real readiness check, not a guessed fixed delay.
   `FIELD_SELECTOR` was promoted from a `filler.py`-private constant to a
   shared one for exactly this reuse, one definition of "a fillable
   field" instead of two that could drift. Proved this was a genuine fix,
   not luck, by making `test_form_server.py`'s `ashby-like` application
   route insert its field via a real delayed script (300ms) instead of
   being present immediately — the existing
   `test_ashby_navigates_to_the_real_application_url` test now fails
   without the wait and passes with it, a real regression test rather
   than a fixture that happened not to exercise the bug.

   Re-run against the same live Ramp posting after the fix: real success
   — `status=awaiting_confirmation`, `risk_level=high` (first application
   to this company), **2.3s** real wall time, all 7 real fields answered
   from the profile (a scripted fake LLM client, same precedent
   `test_autoapply_planner.py`'s own smoke tests already use, since this
   step verifies the ATS integration mechanics end-to-end, not per-field
   answer quality — that's `test_autoapply_answers.py`'s job). Never
   confirmed; the application only exists in an in-memory test session,
   not `hirable.db`. `pytest` (493 passed) / `mypy` / `ruff check` /
   `ruff format --check` all green. Ashby thread (steps 1-5) complete.

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
