import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { RunKind, Schedule } from '../api/types'
import { useApi } from '../hooks/useApi'
import { SOURCES } from '../lib/sources'
import { formatTime } from '../lib/format'
import { Button } from './ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'

const HOURS_OPTIONS = [1, 6, 12, 24, 24 * 7]

function ScheduleRow({ schedule, onToggled }: { schedule: Schedule; onToggled: () => void }) {
  async function toggle() {
    try {
      await apiPost(`/schedules/${schedule.id}/toggle`, { enabled: !schedule.enabled })
      onToggled()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <li className="flex items-center justify-between py-2 text-sm">
      <div>
        <span className="font-medium text-foreground">
          {schedule.kind} / {schedule.source}
        </span>
        <span className="ml-2 text-muted-foreground">every {schedule.every_hours}h</span>
        <p className="text-xs text-muted-foreground">
          last run: {schedule.last_run_at ? formatTime(schedule.last_run_at) : 'never'}
        </p>
      </div>
      <Button variant={schedule.enabled ? 'secondary' : 'outline'} size="sm" onClick={() => void toggle()}>
        {schedule.enabled ? 'Enabled' : 'Paused'}
      </Button>
    </li>
  )
}

// A small always-visible dashboard section (PHASE2.md step 6) — no modal,
// just an inline create row plus the toggle list.
export function SchedulesPanel() {
  const schedules = useApi<Schedule[]>('/schedules')
  const [kind, setKind] = useState<RunKind>('jobs')
  const [source, setSource] = useState(SOURCES.jobs[0] ?? '')
  const [everyHours, setEveryHours] = useState(24)
  const [busy, setBusy] = useState(false)

  function selectKind(next: RunKind) {
    setKind(next)
    setSource(SOURCES[next][0] ?? '')
  }

  async function create() {
    setBusy(true)
    try {
      await apiPost('/schedules', { kind, source, every_hours: everyHours })
      toast.success(`Scheduled ${kind}/${source} every ${everyHours}h`)
      schedules.reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-border bg-card p-5">
      <h2 className="text-sm font-semibold text-foreground">Scheduled scrapes</h2>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Select value={kind} onValueChange={(v) => selectKind(v as RunKind)}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="jobs">jobs</SelectItem>
            <SelectItem value="questions">questions</SelectItem>
          </SelectContent>
        </Select>
        <Select value={source} onValueChange={(v) => setSource(v ?? '')}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SOURCES[kind].map((s) => (
              <SelectItem key={s} value={s}>
                {s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={String(everyHours)} onValueChange={(v) => setEveryHours(Number(v))}>
          <SelectTrigger className="w-28">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HOURS_OPTIONS.map((h) => (
              <SelectItem key={h} value={String(h)}>
                every {h}h
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" disabled={busy || source === ''} onClick={() => void create()}>
          Add
        </Button>
      </div>

      {schedules.data && schedules.data.length > 0 && (
        <ul className="mt-3 divide-y divide-border">
          {schedules.data.map((schedule) => (
            <ScheduleRow key={schedule.id} schedule={schedule} onToggled={schedules.reload} />
          ))}
        </ul>
      )}
    </div>
  )
}
