import { useEffect, useState } from 'react'

import { apiPost } from '../api/client'
import type { Paginated, Run, Stats } from '../api/types'
import { NewScrapeModal } from '../components/NewScrapeModal'
import { useApi } from '../hooks/useApi'
import { formatPercent, formatTime } from '../lib/format'

const STATUS_STYLE: Record<Run['status'], string> = {
  running: 'bg-indigo-50 text-indigo-700',
  completed: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-rose-50 text-rose-700',
  cancelled: 'bg-slate-100 text-slate-600',
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-5">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
    </div>
  )
}

function StatusBadge({ status }: { status: Run['status'] }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_STYLE[status]}`}>
      {status}
    </span>
  )
}

function RunRow({ run, onCancel }: { run: Run; onCancel: (id: number) => void }) {
  return (
    <tr className="border-t border-slate-100">
      <td className="px-4 py-3 text-slate-500">#{run.id}</td>
      <td className="px-4 py-3">
        {run.kind} / {run.source}
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={run.status} />
      </td>
      <td className="px-4 py-3 text-right">{run.pages_fetched}</td>
      <td className="px-4 py-3 text-right">{run.items_saved}</td>
      <td className="px-4 py-3 text-right">{run.errors.length}</td>
      <td className="px-4 py-3 text-slate-500">{formatTime(run.started_at)}</td>
      <td className="px-4 py-3 text-right">
        {run.status === 'running' && !run.cancel_requested && (
          <button
            type="button"
            className="text-xs font-medium text-rose-600 hover:text-rose-800"
            onClick={() => onCancel(run.id)}
          >
            Cancel
          </button>
        )}
      </td>
    </tr>
  )
}

export function Dashboard() {
  const [showModal, setShowModal] = useState(false)
  // Poll every 3s while a run is active so the counters tick live (DESIGN.md §6).
  const [pollMs, setPollMs] = useState<number | undefined>(undefined)
  const runs = useApi<Paginated<Run>>('/runs', pollMs)
  const stats = useApi<Stats>('/stats', pollMs)
  const anyActive = runs.data?.items.some((run) => run.status === 'running') ?? false

  useEffect(() => {
    setPollMs(anyActive ? 3000 : undefined)
  }, [anyActive])

  async function cancelRun(id: number) {
    await apiPost(`/runs/${id}/cancel`)
    runs.reload()
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
        <button
          type="button"
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white
            hover:bg-indigo-700"
          onClick={() => setShowModal(true)}
        >
          New scrape
        </button>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Jobs" value={String(stats.data?.jobs ?? '—')} />
        <StatCard label="Questions" value={String(stats.data?.questions ?? '—')} />
        <StatCard label="Companies" value={String(stats.data?.companies ?? '—')} />
        <StatCard
          label="Escalation rate"
          value={stats.data ? formatPercent(stats.data.escalation_rate) : '—'}
        />
      </div>

      <div className="mt-8 overflow-hidden rounded-xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Recent runs</h2>
          {runs.error && <span className="text-xs text-rose-600">{runs.error}</span>}
        </div>
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Run</th>
              <th className="px-4 py-2 font-medium">Kind / source</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 text-right font-medium">Pages</th>
              <th className="px-4 py-2 text-right font-medium">Saved</th>
              <th className="px-4 py-2 text-right font-medium">Errors</th>
              <th className="px-4 py-2 font-medium">Started</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {(runs.data?.items ?? []).map((run) => (
              <RunRow key={run.id} run={run} onCancel={(id) => void cancelRun(id)} />
            ))}
          </tbody>
        </table>
        {runs.data?.items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-slate-400">
            No runs yet — start one with “New scrape”.
          </p>
        )}
      </div>

      {showModal && (
        <NewScrapeModal onClose={() => setShowModal(false)} onStarted={() => runs.reload()} />
      )}
    </div>
  )
}
