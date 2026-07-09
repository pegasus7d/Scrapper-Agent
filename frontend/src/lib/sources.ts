import type { RunKind } from '../api/types'

// Mirrors JOB_SOURCES / QUESTION_SOURCES in backend/scraper/sources/__init__.py.
export const SOURCES: Record<RunKind, string[]> = {
  jobs: ['hn', 'remoteok', 'weworkremotely', 'arbeitnow'],
  questions: ['hn-interviews'],
}
