import { useState } from 'react'

import type { Job, Paginated } from '../api/types'
import { Drawer } from '../components/Drawer'
import { Pagination } from '../components/Pagination'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'

const LIMIT = 20

function jobsPath(q: string, company: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
  if (q) params.set('q', q)
  if (company) params.set('company', company)
  return `/jobs?${params.toString()}`
}

function JobDrawer({ job, onClose }: { job: Job; onClose: () => void }) {
  return (
    <Drawer title={job.title} onClose={onClose}>
      <p className="mt-1 text-sm text-slate-500">
        {job.company}
        {job.location && ` · ${job.location}`}
        {job.salary && ` · ${job.salary}`}
      </p>
      {job.requirements.length > 0 && (
        <>
          <h3 className="mt-6 text-sm font-semibold text-slate-900">Requirements</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
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
      <p className="mt-6 text-xs text-slate-400">
        {job.source} · {job.extraction_tier} tier · scraped {formatTime(job.scraped_at)}
      </p>
    </Drawer>
  )
}

const inputStyle =
  'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ' +
  'placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none'

export function Jobs() {
  const [q, setQ] = useState('')
  const [company, setCompany] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Job | null>(null)
  const jobs = useApi<Paginated<Job>>(jobsPath(q, company, offset))

  function updateFilter(setter: (value: string) => void) {
    return (value: string) => {
      setter(value)
      setOffset(0)
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Jobs</h1>
        <div className="flex gap-2">
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
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white">
        {jobs.error && <p className="px-4 py-3 text-sm text-rose-600">{jobs.error}</p>}
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Title</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Location</th>
              <th className="px-4 py-2 font-medium">Salary</th>
              <th className="px-4 py-2 font-medium">Source</th>
              <th className="px-4 py-2 font-medium">Scraped</th>
            </tr>
          </thead>
          <tbody>
            {(jobs.data?.items ?? []).map((job) => (
              <tr
                key={job.id}
                className="cursor-pointer border-t border-slate-100 hover:bg-indigo-50/40"
                onClick={() => setSelected(job)}
              >
                <td className="px-4 py-3 font-medium text-slate-900">{job.title}</td>
                <td className="px-4 py-3">{job.company}</td>
                <td className="px-4 py-3 text-slate-500">{job.location ?? '—'}</td>
                <td className="px-4 py-3 text-slate-500">{job.salary ?? '—'}</td>
                <td className="px-4 py-3 text-slate-500">{job.source}</td>
                <td className="px-4 py-3 text-slate-500">{formatTime(job.scraped_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {jobs.data?.items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-slate-400">No jobs match.</p>
        )}
        {jobs.data && (
          <Pagination
            offset={offset}
            limit={LIMIT}
            total={jobs.data.total}
            onOffset={setOffset}
          />
        )}
      </div>

      {selected && <JobDrawer job={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
