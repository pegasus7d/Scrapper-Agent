# Job & Interview-Question Scraper Agent — Idea Doc

## What this is
An AI agent that scrapes the web to collect:
1. **Job postings** (title, company, salary, requirements, links)
2. **Interview questions** asked by companies (from public discussion sources)

## Core approach
- **Fetch layer:** `scrapling` (Python) — stealthy, adaptive scraper. Handles JS-rendered
  pages and survives site layout changes better than raw requests/bs4/Selenium.
- **Extraction layer:** LLM-based, not hardcoded selectors — because job boards and
  discussion sites vary wildly in structure. Feed the LLM cleaned markdown/text from
  Scrapling, not raw HTML (keeps token usage down).
- **Cascade / router pattern for cost control:**
  - Use a cheap/small/free model (e.g. local via Ollama, or a low-cost API model) for
    the repetitive, narrow extraction calls ("pull these fields from this clean text").
  - Escalate to a stronger/frontier model only when extraction fails validation or
    confidence is low.
  - Rationale: narrow, well-specified extraction tasks don't need frontier-level
    reasoning if the harness (tight schema, validation, retries) is good. Planning /
    ambiguous-page handling still benefits from a stronger model.
- **Validation:** `pydantic` schemas force LLM output into a strict shape and catch bad
  extractions immediately (triggers escalation).
- **Storage:** SQLite (or JSON to start), deduped by source URL.
- **Orchestration:** a simple loop, not a heavy agent framework (LangChain/CrewAI/AutoGen
  add token overhead we don't need). Options considered: hand-rolled tool-calling loop,
  or `smolagents` (code-first, more token-efficient than JSON-heavy frameworks).

## Data schemas (draft)

```python
class Job(BaseModel):
    title: str
    company: str
    location: str | None
    salary: str | None
    requirements: list[str]
    posting_url: str      # page we scraped
    apply_url: str | None # raw href, don't resolve redirects (extra request cost)

class InterviewQuestion(BaseModel):
    company: str
    role: str | None
    question: str
    round: str | None      # e.g. "phone screen", "onsite"
    source_url: str
```

## Pipeline (same shape for both jobs and interview questions)
1. Seed list of source URLs.
2. Scrapling fetches page → cleaned text/markdown.
3. Cheap model extracts JSON against schema.
4. Validate with Pydantic — on failure/low confidence, retry with stronger model.
5. Dedupe on URL, write to storage.
6. If page has pagination / related links, queue those next.

```python
for url in queue:
    page = fetch(url)              # scrapling
    data = extract(page, schema)   # cheap model, escalate on failure
    save(data)
    queue.extend(find_next_links(page))
```

## Candidate sources
- **Jobs:** open job boards (avoid ones whose ToS explicitly forbids scraping, e.g.
  LinkedIn/Indeed — flagged as higher legal risk, deprioritize or handle carefully).
- **Interview questions:** LeetCode Discuss (company-tagged threads), Blind, relevant
  subreddits (e.g. r/cscareerquestions) — generally easier/lower-friction than
  Glassdoor, which gates interview reviews behind login + has strong anti-bot measures.

## Build order (MVP first, don't build both scrapers at once)
1. Pick **one** job source, get the full pipeline (fetch → extract → validate → store)
   working end-to-end.
2. Pick **one** interview-question source (e.g. LeetCode Discuss), do the same.
3. Only after both MVPs work, generalize by swapping in more seed URLs/sources.

## Decisions since this doc was written (authoritative details in DESIGN.md)
- MVP sources: **Hacker News "Who is hiring?"** for jobs, **Reddit** (public `.json`
  endpoints) for interview questions. LeetCode Discuss/Blind deferred (JS-heavy,
  anti-bot).
- Local model: **qwen2.5:7b-instruct via Ollama**; escalation tier: Claude Haiku.
- Full technical contract (DB models, chunking, API, tests): see [[DESIGN.md]].

## Open questions / not yet decided
- Whether resume parsing should feed into job matching (separate feature, not scoped
  yet — resumes are PDFs/DOCX, so that's document parsing, not web scraping, and would
  use a different extraction path: `pdfplumber`/`python-docx` → LLM field extraction).
