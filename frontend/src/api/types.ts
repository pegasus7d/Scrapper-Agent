// Hand-written mirrors of the backend response models (DESIGN.md §4).
// Update this file whenever a response model in backend/api/routes.py changes.

export type RunKind = 'jobs' | 'questions'

export interface RunError {
  url: string
  error: string
}

export interface Run {
  id: number
  kind: string
  source: string
  model: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  cancel_requested: boolean
  started_at: string
  finished_at: string | null
  pages_fetched: number
  items_saved: number
  items_duplicate: number
  escalations: number
  errors: RunError[]
}

export interface Job {
  id: number
  title: string
  company: string
  location: string | null
  salary: string | null
  requirements: string[]
  posting_url: string
  apply_url: string | null
  source: string
  extraction_tier: string
  scraped_at: string
  starred: boolean
}

export interface Question {
  id: number
  company: string | null
  role: string | null
  question: string
  round: string | null
  source_url: string
  source: string
  extraction_tier: string
  scraped_at: string
}

export interface RunCreated {
  run_id: number
}

export interface Paginated<T> {
  items: T[]
  total: number
}

export interface Stats {
  jobs: number
  questions: number
  companies: number
  escalation_rate: number
}

export interface Schedule {
  id: number
  kind: string
  source: string
  every_hours: number
  enabled: boolean
  last_run_at: string | null
}

export interface LocalModel {
  name: string
  size_bytes: number
}

export interface ResumeMarkdown {
  markdown: string
}

export interface ResumePositions {
  positions: string[]
}

export interface Company {
  id: number
  name: string
  slug: string | null
  ats_provider: string | null
  discovered_at: string
  last_checked_at: string | null
}

export interface DiscoveryResult {
  discovered: number
  total: number
}

export interface ResolutionResult {
  checked: number
  resolved: number
}
