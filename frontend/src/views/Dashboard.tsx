import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { Paginated, Run, Stats } from '../api/types'
import { AnimatedNumber } from '../components/AnimatedNumber'
import { NewScrapeModal } from '../components/NewScrapeModal'
import { RunProgressPanel } from '../components/RunProgressPanel'
import { RunsChart } from '../components/RunsChart'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table'
import { useApi } from '../hooks/useApi'
import { formatPercent, formatTime } from '../lib/format'

const STATUS_STYLE: Record<Run['status'], string> = {
  running: 'bg-indigo-50 text-indigo-700',
  completed: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-rose-50 text-rose-700',
  cancelled: 'bg-muted text-muted-foreground',
}

function StatCard({
  label,
  value,
  formatter,
}: {
  label: string
  value: number | null
  formatter?: (n: number) => string
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <p className="text-sm text-muted-foreground">{label}</p>
      {value === null ? (
        <Skeleton className="mt-2 h-7 w-16" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-foreground">
          <AnimatedNumber value={value} formatter={formatter} />
        </p>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: Run['status'] }) {
  return <Badge className={STATUS_STYLE[status]}>{status}</Badge>
}

function RunRow({ run, onCancel }: { run: Run; onCancel: (id: number) => void }) {
  return (
    <TableRow>
      <TableCell className="text-muted-foreground">#{run.id}</TableCell>
      <TableCell>
        {run.kind} / {run.source}
      </TableCell>
      <TableCell>
        <StatusBadge status={run.status} />
      </TableCell>
      <TableCell className="text-right">{run.pages_fetched}</TableCell>
      <TableCell className="text-right">{run.items_saved}</TableCell>
      <TableCell className="text-right">{run.errors.length}</TableCell>
      <TableCell className="text-muted-foreground">{formatTime(run.started_at)}</TableCell>
      <TableCell className="text-right">
        {run.status === 'running' && !run.cancel_requested && (
          <Button variant="ghost" size="xs" onClick={() => onCancel(run.id)}>
            Cancel
          </Button>
        )}
      </TableCell>
    </TableRow>
  )
}

// Fires a toast the moment a run's status flips from "running" to a terminal
// state — the dashboard already polls every 3s while a run is active, this
// just surfaces the transition instead of leaving it to a silent badge change.
function useRunLifecycleToasts(runs: Run[]) {
  const previous = useRef(new Map<number, Run['status']>())
  useEffect(() => {
    for (const run of runs) {
      const before = previous.current.get(run.id)
      if (before === 'running' && run.status !== 'running') {
        const label = `Run #${run.id} (${run.kind}/${run.source})`
        if (run.status === 'completed') toast.success(`${label} completed — ${run.items_saved} saved`)
        else if (run.status === 'failed') toast.error(`${label} failed`)
        else toast.info(`${label} cancelled`)
      }
      previous.current.set(run.id, run.status)
    }
  }, [runs])
}

export function Dashboard() {
  const [showModal, setShowModal] = useState(false)
  // Poll every 3s while a run is active so the counters tick live (DESIGN.md §6).
  const [pollMs, setPollMs] = useState<number | undefined>(undefined)
  const runs = useApi<Paginated<Run>>('/runs', pollMs)
  const stats = useApi<Stats>('/stats', pollMs)
  const runItems = runs.data?.items ?? []
  const activeRun = runItems.find((run) => run.status === 'running')

  useEffect(() => {
    setPollMs(activeRun ? 3000 : undefined)
  }, [activeRun])

  useRunLifecycleToasts(runItems)

  async function cancelRun(id: number) {
    await apiPost(`/runs/${id}/cancel`)
    runs.reload()
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
        <Button onClick={() => setShowModal(true)}>New scrape</Button>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label="Jobs" value={stats.data?.jobs ?? null} />
        <StatCard label="Questions" value={stats.data?.questions ?? null} />
        <StatCard label="Companies" value={stats.data?.companies ?? null} />
        <StatCard
          label="Escalation rate"
          value={stats.data?.escalation_rate ?? null}
          formatter={formatPercent}
        />
      </div>

      {activeRun && (
        <div className="mt-6">
          <RunProgressPanel run={activeRun} />
        </div>
      )}

      {runItems.length > 0 && (
        <div className="mt-6 rounded-xl border border-border bg-card p-5">
          <h2 className="text-sm font-semibold text-foreground">Items per run</h2>
          <RunsChart runs={runItems} />
        </div>
      )}

      <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        <div className="flex items-center justify-between px-4 py-3">
          <h2 className="text-sm font-semibold text-foreground">Recent runs</h2>
          {runs.error && <span className="text-xs text-rose-600">{runs.error}</span>}
        </div>
        {runItems.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-4 py-12 text-center">
            <p className="text-sm text-muted-foreground">No runs yet.</p>
            <Button variant="outline" onClick={() => setShowModal(true)}>
              Start your first scrape
            </Button>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Kind / source</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Pages</TableHead>
                <TableHead className="text-right">Saved</TableHead>
                <TableHead className="text-right">Errors</TableHead>
                <TableHead>Started</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {runItems.map((run) => (
                <RunRow key={run.id} run={run} onCancel={(id) => void cancelRun(id)} />
              ))}
            </TableBody>
          </Table>
        )}
      </div>

      {showModal && (
        <NewScrapeModal onClose={() => setShowModal(false)} onStarted={() => runs.reload()} />
      )}
    </div>
  )
}
