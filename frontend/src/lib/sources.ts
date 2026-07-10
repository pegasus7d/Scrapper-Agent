import type { DiscoverySource, RunKind } from '../api/types'

// Mirrors JOB_SOURCES / QUESTION_SOURCES in backend/scraper/sources/__init__.py.
export const SOURCES: Record<RunKind, string[]> = {
  jobs: ['hn', 'remoteok', 'weworkremotely', 'arbeitnow', 'himalayas', 'remotejobs'],
  questions: ['hn-interviews', 'github-questions', 'faqguru-questions'],
}

// Company discovery sources are no longer hand-mirrored here (PHASE9.md
// step 2, after they drifted out of sync once already) — fetch them for
// real from GET /companies/sources (DiscoverySource in api/types.ts) and
// look up a label with this helper, falling back to the raw name if the
// fetch hasn't landed yet or the name is somehow unknown.
export function labelFor(sources: DiscoverySource[] | null, name: string): string {
  return sources?.find((s) => s.name === name)?.label ?? name
}
