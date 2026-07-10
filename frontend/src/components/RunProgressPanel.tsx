import { useEffect, useState } from 'react'

import type { Run } from '../api/types'
import { AnimatedNumber } from './AnimatedNumber'
import { Badge } from './ui/badge'
import { useChangeFlash } from '../hooks/useChangeFlash'

interface Props {
  run: Run
}

const TICK_MS = 1000

function elapsedLabel(startedAt: string, now: number): string {
  const utc = startedAt.endsWith('Z') || startedAt.includes('+') ? startedAt : `${startedAt}Z`
  const seconds = Math.max(0, Math.floor((now - new Date(utc).getTime()) / 1000))
  const minutes = Math.floor(seconds / 60)
  return minutes > 0 ? `${minutes}m ${seconds % 60}s` : `${seconds}s`
}

function Stat({ label, value }: { label: string; value: number }) {
  const flashing = useChangeFlash(value)
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd
        className={`text-lg font-semibold transition-colors duration-500 ${
          flashing ? 'text-indigo-600 dark:text-indigo-400' : 'text-foreground'
        }`}
      >
        <AnimatedNumber value={value} />
      </dd>
    </div>
  )
}

// Live detail card for the one run that can currently be "running" — the
// dashboard's stat cards and table already poll every 3s, this just surfaces
// the same numbers up close, plus the most recent errors as they land.
// Richer feedback (PHASE8.md step 4) than a bare number swap: each stat
// counts up (AnimatedNumber, already used on the dashboard's own stat
// cards) and briefly flashes color on a real change (useChangeFlash), and
// a live elapsed-time ticker gives constant motion even between SSE
// frames — all hand-rolled CSS transitions/setInterval, no animation
// library (frontend/CLAUDE.md).
export function RunProgressPanel({ run }: Props) {
  const recentErrors = run.errors.slice(-3).reverse()
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), TICK_MS)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="rounded-xl border border-indigo-200 bg-indigo-50/40 p-5 dark:border-indigo-900 dark:bg-indigo-950/30">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-indigo-500 opacity-75" />
            <span className="relative inline-flex size-2 rounded-full bg-indigo-600" />
          </span>
          <h2 className="text-sm font-semibold text-foreground">
            Run #{run.id} — {run.kind} / {run.source}
          </h2>
          <span className="text-xs tabular-nums text-muted-foreground">
            {elapsedLabel(run.started_at, now)}
          </span>
        </div>
        <Badge variant="secondary">running</Badge>
      </div>

      <dl className="mt-4 grid grid-cols-4 gap-4 text-center">
        <Stat label="Pages" value={run.pages_fetched} />
        <Stat label="Saved" value={run.items_saved} />
        <Stat label="Duplicates" value={run.items_duplicate} />
        <Stat label="Errors" value={run.errors.length} />
      </dl>

      {recentErrors.length > 0 && (
        <ul className="mt-4 space-y-1 border-t border-indigo-100 pt-3 text-xs text-muted-foreground dark:border-indigo-900">
          {recentErrors.map((error) => (
            <li key={`${error.url}-${error.error}`} className="truncate">
              <span className="font-medium text-rose-600">error</span> {error.url}: {error.error}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
