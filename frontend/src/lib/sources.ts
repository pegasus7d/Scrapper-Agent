import type { RunKind } from '../api/types'

// Mirrors JOB_SOURCES / QUESTION_SOURCES in backend/scraper/sources/__init__.py.
export const SOURCES: Record<RunKind, string[]> = {
  jobs: ['hn', 'remoteok', 'weworkremotely', 'arbeitnow', 'himalayas', 'remotejobs'],
  questions: ['hn-interviews', 'github-questions', 'faqguru-questions'],
}

// Mirrors DISCOVERY_SOURCES in backend/scraper/discovery.py (PHASE8.md step 9).
export const COMPANY_DISCOVERY_SOURCES = [
  'yc',
  'largest_us_companies',
  'a16z',
  'sequoia',
  'foundersfund',
  'bvp',
] as const
