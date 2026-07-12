import { useState } from 'react'

import type { LocalModel, RunKind, SourceHealth } from '../api/types'
import { useApi } from '../hooks/useApi'
import { formatSize } from '../lib/format'
import { SOURCES } from '../lib/sources'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from './ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select'

// PHASE12.md step 1: a source's last-checked liveness, hover for detail.
const HEALTH_DOT_CLASS: Record<SourceHealth['status'], string> = {
  ok: 'bg-green-500',
  blocked: 'bg-amber-500',
  unreachable: 'bg-red-500',
}

interface Props {
  onClose: () => void
  // The backend keeps its one-run-at-a-time invariant (DESIGN.md §6) — the
  // parent owns running the selected sources one at a time so the queue
  // survives this modal closing. `model` is undefined for "use the app
  // default" (PHASE6.md step 3).
  onStart: (kind: RunKind, sources: string[], model: string | undefined) => void
}

export function NewScrapeModal({ onClose, onStart }: Props) {
  const [kind, setKind] = useState<RunKind>('jobs')
  const [selected, setSelected] = useState<string[]>([])
  const [model, setModel] = useState<string | undefined>(undefined)
  // Only genuinely-installed models are ever offered (PHASE6.md step 3) —
  // never a hardcoded list.
  const models = useApi<LocalModel[]>('/models')
  // Fetched fresh every time this modal opens (PHASE12.md step 1) — a
  // cheap liveness probe, not cached state that could go stale while the
  // modal sits open.
  const health = useApi<SourceHealth[]>('/sources/health')
  const healthByName = new Map(health.data?.map((h) => [h.name, h]))

  function selectKind(next: RunKind) {
    setKind(next)
    setSelected([])
  }

  function toggleSource(source: string, checked: boolean) {
    setSelected((prev) => (checked ? [...prev, source] : prev.filter((s) => s !== source)))
  }

  function start() {
    onStart(kind, selected, model)
    onClose()
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New scrape</DialogTitle>
        </DialogHeader>

        <label className="block text-sm font-medium text-muted-foreground">
          Kind
          <Select value={kind} onValueChange={(v) => selectKind(v as RunKind)}>
            <SelectTrigger className="mt-1 w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="jobs">jobs</SelectItem>
              <SelectItem value="questions">questions</SelectItem>
            </SelectContent>
          </Select>
        </label>

        <div className="block text-sm font-medium text-muted-foreground">
          Sources
          <div className="mt-1 flex flex-col gap-2">
            {SOURCES[kind].map((s) => {
              const sourceHealth = healthByName.get(s)
              return (
                <label
                  key={s}
                  className="flex items-center gap-2 text-sm font-normal text-foreground"
                  title={sourceHealth?.detail ?? undefined}
                >
                  <Checkbox
                    checked={selected.includes(s)}
                    onCheckedChange={(checked) => toggleSource(s, checked === true)}
                  />
                  {sourceHealth && (
                    <span
                      className={`inline-block size-2 rounded-full ${HEALTH_DOT_CLASS[sourceHealth.status]}`}
                    />
                  )}
                  {s}
                </label>
              )
            })}
          </div>
        </div>
        {SOURCES[kind].length === 0 && (
          <p className="text-xs text-muted-foreground">No sources for this kind yet.</p>
        )}

        {models.data && models.data.length > 0 && (
          <label className="block text-sm font-medium text-muted-foreground">
            Model
            <Select
              value={model ?? models.data[0].name}
              onValueChange={(v) => setModel(v ?? undefined)}
            >
              <SelectTrigger className="mt-1 w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {models.data.map((m) => (
                  <SelectItem key={m.name} value={m.name}>
                    {m.name} ({formatSize(m.size_bytes)})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </label>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={selected.length === 0} onClick={start}>
            Start {selected.length > 1 ? `(${selected.length})` : ''}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
