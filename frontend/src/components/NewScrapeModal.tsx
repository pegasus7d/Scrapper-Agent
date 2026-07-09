import { useState } from 'react'

import { apiPost } from '../api/client'
import type { RunCreated, RunKind } from '../api/types'

// Mirrors JOB_SOURCES / QUESTION_SOURCES in backend/scraper/sources.py.
const SOURCES: Record<RunKind, string[]> = {
  jobs: ['hn'],
  questions: [],
}

interface Props {
  onClose: () => void
  onStarted: () => void
}

export function NewScrapeModal({ onClose, onStarted }: Props) {
  const [kind, setKind] = useState<RunKind>('jobs')
  const [source, setSource] = useState(SOURCES.jobs[0] ?? '')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  function selectKind(next: RunKind) {
    setKind(next)
    setSource(SOURCES[next][0] ?? '')
  }

  async function start() {
    setBusy(true)
    setError(null)
    try {
      await apiPost<RunCreated>('/runs', { kind, source })
      onStarted()
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
  }

  const selectStyle =
    'w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ' +
    'focus:border-indigo-400 focus:outline-none'

  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/30">
      <div className="w-80 rounded-xl bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-slate-900">New scrape</h2>
        <label className="mt-4 block text-sm font-medium text-slate-600">
          Kind
          <select
            className={selectStyle}
            value={kind}
            onChange={(e) => selectKind(e.target.value as RunKind)}
          >
            <option value="jobs">jobs</option>
            <option value="questions">questions</option>
          </select>
        </label>
        <label className="mt-3 block text-sm font-medium text-slate-600">
          Source
          <select
            className={selectStyle}
            value={source}
            onChange={(e) => setSource(e.target.value)}
          >
            {SOURCES[kind].map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        {SOURCES[kind].length === 0 && (
          <p className="mt-2 text-xs text-slate-500">No sources for this kind yet.</p>
        )}
        {error && <p className="mt-3 text-sm text-rose-600">{error}</p>}
        <div className="mt-6 flex justify-end gap-2">
          <button
            type="button"
            className="rounded-lg px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white
              hover:bg-indigo-700 disabled:opacity-50"
            disabled={busy || source === ''}
            onClick={() => void start()}
          >
            Start
          </button>
        </div>
      </div>
    </div>
  )
}
