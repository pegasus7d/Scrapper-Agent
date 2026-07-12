import { Star } from 'lucide-react'
import type { MouseEvent } from 'react'
import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost, apiUrl } from '../api/client'
import type { Job, Paginated, Question } from '../api/types'
import { Drawer } from '../components/Drawer'
import { Pagination } from '../components/Pagination'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../components/ui/select'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'
import { JOB_STATUSES, statusLabel } from '../lib/jobStatus'

const LIMIT = 20
const ALL_STATUSES = 'all'

function jobsPath(
  q: string,
  company: string,
  starredOnly: boolean,
  status: string,
  offset: number,
): string {
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
  if (q) params.set('q', q)
  if (company) params.set('company', company)
  if (starredOnly) params.set('starred', 'true')
  if (status !== ALL_STATUSES) params.set('status', status)
  return `/jobs?${params.toString()}`
}

function exportPath(
  format: 'csv' | 'json',
  q: string,
  company: string,
  starredOnly: boolean,
  status: string,
): string {
  const params = new URLSearchParams({ format })
  if (q) params.set('q', q)
  if (company) params.set('company', company)
  if (starredOnly) params.set('starred', 'true')
  if (status !== ALL_STATUSES) params.set('status', status)
  return apiUrl(`/jobs/export?${params.toString()}`)
}

function statusBadgeVariant(status: string): 'outline' | 'secondary' | 'default' | 'destructive' {
  if (status === 'none') return 'outline'
  if (status === 'rejected') return 'destructive'
  if (status === 'offer') return 'default'
  return 'secondary'
}

function StarButton({ job, onToggled }: { job: Job; onToggled: () => void }) {
  async function toggle(e: MouseEvent) {
    e.stopPropagation()
    try {
      await apiPost(`/jobs/${job.id}/star`, { starred: !job.starred })
      onToggled()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <button type="button" onClick={(e) => void toggle(e)} aria-label="Toggle star">
      <Star
        className={`size-4 ${job.starred ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground'}`}
      />
    </button>
  )
}

function StatusControl({ job, onChanged }: { job: Job; onChanged: (job: Job) => void }) {
  const [updating, setUpdating] = useState(false)

  async function change(status: string) {
    setUpdating(true)
    try {
      const updated = await apiPost<Job>(`/jobs/${job.id}/status`, { status })
      onChanged(updated)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setUpdating(false)
    }
  }

  return (
    <Select value={job.status} onValueChange={(value) => value && void change(value)}>
      <SelectTrigger className="mt-3 w-48" disabled={updating}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {JOB_STATUSES.map((status) => (
          <SelectItem key={status} value={status}>
            {statusLabel(status)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

// Surfaces the existing interview-question bank once a job's status flips
// to "interviewing" (PHASE10.md step 9) -- wiring two already-existing
// features together, not a new question-storage mechanism. The fetch
// itself is skipped (useApi's path=null) for every other status, not just
// the rendered section.
function InterviewQuestions({ job }: { job: Job }) {
  const questions = useApi<Paginated<Question>>(
    job.status === 'interviewing' ? `/jobs/${job.id}/interview-questions` : null,
  )
  if (job.status !== 'interviewing' || !questions.data || questions.data.items.length === 0) {
    return null
  }
  return (
    <>
      <h3 className="mt-6 text-sm font-semibold text-foreground">Interview questions</h3>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
        {questions.data.items.map((q) => (
          <li key={q.id}>
            {q.question}
            {q.round && <span className="text-xs"> ({q.round})</span>}
          </li>
        ))}
      </ul>
    </>
  )
}

function JobDrawer({
  job,
  onClose,
  onStatusChanged,
}: {
  job: Job
  onClose: () => void
  onStatusChanged: (job: Job) => void
}) {
  return (
    <Drawer title={job.title} onClose={onClose}>
      <p className="mt-1 text-sm text-muted-foreground">
        {job.company}
        {job.location && ` · ${job.location}`}
        {job.salary && ` · ${job.salary}`}
      </p>
      <StatusControl job={job} onChanged={onStatusChanged} />
      {job.status_changed_at && (
        <p className="mt-1 text-xs text-muted-foreground">
          status changed {formatTime(job.status_changed_at)}
        </p>
      )}
      <InterviewQuestions job={job} />
      {job.requirements.length > 0 && (
        <>
          <h3 className="mt-6 text-sm font-semibold text-foreground">Requirements</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
            {job.requirements.map((requirement) => (
              <li key={requirement}>{requirement}</li>
            ))}
          </ul>
        </>
      )}
      <div className="mt-6 flex flex-col gap-2 text-sm">
        <a
          className="font-medium text-indigo-600 hover:text-indigo-800"
          href={job.posting_url}
          target="_blank"
          rel="noreferrer"
        >
          Posting ↗
        </a>
        {job.apply_url && (
          <a
            className="font-medium text-indigo-600 hover:text-indigo-800"
            href={job.apply_url}
            target="_blank"
            rel="noreferrer"
          >
            Apply ↗
          </a>
        )}
      </div>
      <p className="mt-6 text-xs text-muted-foreground">
        {job.source} · {job.extraction_tier} tier · scraped {formatTime(job.scraped_at)}
      </p>
    </Drawer>
  )
}

const inputStyle =
  'rounded-lg border border-border bg-card px-3 py-2 text-sm ' +
  'placeholder:text-muted-foreground focus:border-indigo-400 focus:outline-none'

export function Jobs() {
  const [q, setQ] = useState('')
  const [company, setCompany] = useState('')
  const [starredOnly, setStarredOnly] = useState(false)
  const [status, setStatus] = useState(ALL_STATUSES)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Job | null>(null)
  const jobs = useApi<Paginated<Job>>(jobsPath(q, company, starredOnly, status, offset))

  function updateFilter(setter: (value: string) => void) {
    return (value: string) => {
      setter(value)
      setOffset(0)
    }
  }

  function selectJob(job: Job) {
    setSelected(job)
  }

  function onStatusChanged(updated: Job) {
    setSelected(updated)
    jobs.reload()
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Jobs</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className={inputStyle}
            placeholder="Search titles…"
            value={q}
            onChange={(e) => updateFilter(setQ)(e.target.value)}
          />
          <input
            className={inputStyle}
            placeholder="Company…"
            value={company}
            onChange={(e) => updateFilter(setCompany)(e.target.value)}
          />
          <Select value={status} onValueChange={(v) => updateFilter(setStatus)(v ?? ALL_STATUSES)}>
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_STATUSES}>All statuses</SelectItem>
              {JOB_STATUSES.map((s) => (
                <SelectItem key={s} value={s}>
                  {statusLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant={starredOnly ? 'secondary' : 'outline'}
            size="sm"
            onClick={() => {
              setStarredOnly((v) => !v)
              setOffset(0)
            }}
          >
            <Star className={`size-4 ${starredOnly ? 'fill-amber-400 text-amber-400' : ''}`} />
            Starred
          </Button>
          <a href={exportPath('csv', q, company, starredOnly, status)}>
            <Button variant="outline" size="sm">
              Export CSV
            </Button>
          </a>
          <a href={exportPath('json', q, company, starredOnly, status)}>
            <Button variant="outline" size="sm">
              Export JSON
            </Button>
          </a>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        {jobs.error && <p className="px-4 py-3 text-sm text-rose-600">{jobs.error}</p>}
        <table className="w-full text-left text-sm">
          <thead className="bg-muted text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-2" />
              <th className="px-4 py-2 font-medium">Title</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Location</th>
              <th className="px-4 py-2 font-medium">Salary</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Source</th>
              <th className="px-4 py-2 font-medium">Scraped</th>
            </tr>
          </thead>
          <tbody>
            {(jobs.data?.items ?? []).map((job) => (
              <tr
                key={job.id}
                className="cursor-pointer border-t border-border hover:bg-indigo-50/40"
                onClick={() => selectJob(job)}
              >
                <td className="px-4 py-3">
                  <StarButton job={job} onToggled={jobs.reload} />
                </td>
                <td className="px-4 py-3 font-medium text-foreground">{job.title}</td>
                <td className="px-4 py-3">{job.company}</td>
                <td className="px-4 py-3 text-muted-foreground">{job.location ?? '—'}</td>
                <td className="px-4 py-3 text-muted-foreground">{job.salary ?? '—'}</td>
                <td className="px-4 py-3">
                  {job.status !== 'none' && (
                    <Badge variant={statusBadgeVariant(job.status)}>
                      {statusLabel(job.status)}
                    </Badge>
                  )}
                </td>
                <td className="px-4 py-3 text-muted-foreground">{job.source}</td>
                <td className="px-4 py-3 text-muted-foreground">{formatTime(job.scraped_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {jobs.data?.items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">No jobs match.</p>
        )}
        {jobs.data && (
          <Pagination offset={offset} limit={LIMIT} total={jobs.data.total} onOffset={setOffset} />
        )}
      </div>

      {selected && (
        <JobDrawer
          job={selected}
          onClose={() => setSelected(null)}
          onStatusChanged={onStatusChanged}
        />
      )}
    </div>
  )
}
