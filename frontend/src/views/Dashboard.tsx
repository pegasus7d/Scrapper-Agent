import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { Run, RunKind, Stats } from '../api/types'
import { AnimatedNumber } from '../components/AnimatedNumber'
import { NewScrapeModal } from '../components/NewScrapeModal'
import { RunProgressPanel } from '../components/RunProgressPanel'
import { RunsChart } from '../components/RunsChart'
import { SchedulesPanel } from '../components/SchedulesPanel'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table'
import { useApi } from '../hooks/useApi'
import { useRunsLive } from '../hooks/useRunsLive'
import { formatPercent, formatTime } from '../lib/format'
import type { View } from '../lib/views'

const STATUS_STYLE: Record<Run['status'], string> = {
  running: 'bg-indigo-50 text-indigo-700',
  completed: 'bg-emerald-50 text-emerald-700',
  failed: 'bg-rose-50 text-rose-700',
  cancelled: 'bg-muted text-muted-foreground',
}

// Clickable when there's a real destination view for the number; escalation
// rate has no natural one (neither Jobs nor Questions has an extraction-tier
// filter today) — deliberately left non-interactive rather than forced onto
// a view that wouldn't actually explain the number.
function StatCard({
  label,
  value,
  formatter,
  onClick,
}: {
  label: string
  value: number | null
  formatter?: (n: number) => string
  onClick?: () => void
}) {
  return (
    <button
      type="button"
      disabled={!onClick}
      onClick={onClick}
      className={`rounded-xl border border-border bg-card p-5 text-left ${
        onClick ? 'cursor-pointer hover:border-indigo-300 hover:bg-indigo-50/40' : ''
      }`}
    >
      <p className="text-sm text-muted-foreground">{label}</p>
      {value === null ? (
        <Skeleton className="mt-2 h-7 w-16" />
      ) : (
        <p className="mt-1 text-2xl font-semibold text-foreground">
          <AnimatedNumber value={value} formatter={formatter} />
        </p>
      )}
    </button>
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
        if (run.status === 'completed')
          toast.success(`${label} completed — ${run.items_saved} saved`)
        else if (run.status === 'failed') toast.error(`${label} failed`)
        else toast.info(`${label} cancelled`)
      }
      previous.current.set(run.id, run.status)
    }
  }, [runs])
}

interface Queue {
  sources: string[]
  startedAt: number
}

export function Dashboard({ onNavigate }: { onNavigate: (view: View) => void }) {
  const [showModal, setShowModal] = useState(false)
  const [queue, setQueue] = useState<Queue | null>(null)
  // Runs come from an SSE subscription (PHASE6.md step 6), live the whole
  // time — pollMs now only drives the fallback poll if that connection
  // drops, and the still-poll-based /stats endpoint (out of this step's
  // scope) while a run is active (DESIGN.md §6).
  const [pollMs, setPollMs] = useState<number | undefined>(undefined)
  const runs = useRunsLive(pollMs)
  const stats = useApi<Stats>('/stats', pollMs)
  const runItems = runs.data?.items ?? []
  const activeRun = runItems.find((run) => run.status === 'running')

  // How many of the queue's sources have a run that's reached a terminal
  // status since the batch was submitted — the backend (PHASE5.md step 3)
  // runs them one at a time via a Huey pipeline, lazily creating each run
  // row only when its turn comes up, so this is inferred from /runs rather
  // than tracked client-side.
  const queueDoneCount = queue
    ? runItems.filter(
        (run) =>
          queue.sources.includes(run.source) &&
          run.status !== 'running' &&
          new Date(run.started_at).getTime() >= queue.startedAt,
      ).length
    : 0

  useEffect(() => {
    setPollMs(activeRun || queue ? 3000 : undefined)
  }, [activeRun, queue])

  useEffect(() => {
    if (queue && queueDoneCount >= queue.sources.length) setQueue(null)
  }, [queue, queueDoneCount])

  useRunLifecycleToasts(runItems)

  async function cancelRun(id: number) {
    await apiPost(`/runs/${id}/cancel`)
    runs.reload()
  }

  // The backend keeps its one-run-at-a-time invariant (DESIGN.md §6) — one
  // batch endpoint call queues every selected source as a single Huey
  // pipeline that runs them in order, surviving a browser refresh unlike
  // phase 4's client-side sequencing.
  async function startQueue(kind: RunKind, sources: string[], model: string | undefined) {
    setQueue({ sources, startedAt: Date.now() })
    try {
      await apiPost('/runs/batch', { kind, sources, model })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
      setQueue(null)
      return
    }
    runs.reload()
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Dashboard</h1>
        <div className="flex items-center gap-3">
          {queue && (
            <p className="text-sm text-muted-foreground">
              Scraping {queueDoneCount + 1} of {queue.sources.length}:{' '}
              {queue.sources[queueDoneCount]}…
            </p>
          )}
          <Button disabled={queue !== null} onClick={() => setShowModal(true)}>
            New scrape
          </Button>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-5">
        <StatCard
          label="Jobs"
          value={stats.data?.jobs ?? null}
          onClick={() => onNavigate('jobs')}
        />
        <StatCard
          label="Questions"
          value={stats.data?.questions ?? null}
          onClick={() => onNavigate('questions')}
        />
        <StatCard
          label="Companies hiring"
          value={stats.data?.companies ?? null}
          onClick={() => onNavigate('jobs')}
        />
        <StatCard
          label="Discovered companies"
          value={stats.data?.discovered_companies ?? null}
          onClick={() => onNavigate('companies')}
        />
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

      <div className="mt-6">
        <SchedulesPanel />
      </div>

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
        <NewScrapeModal
          onClose={() => setShowModal(false)}
          onStart={(kind, sources, model) => void startQueue(kind, sources, model)}
        />
      )}
    </div>
  )
}
