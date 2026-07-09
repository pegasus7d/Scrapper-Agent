import { useState } from 'react'

import type { RunKind } from '../api/types'
import { SOURCES } from '../lib/sources'
import { Button } from './ui/button'
import { Checkbox } from './ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from './ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from './ui/select'

interface Props {
  onClose: () => void
  // The backend keeps its one-run-at-a-time invariant (DESIGN.md §6) — the
  // parent owns running the selected sources one at a time so the queue
  // survives this modal closing.
  onStart: (kind: RunKind, sources: string[]) => void
}

export function NewScrapeModal({ onClose, onStart }: Props) {
  const [kind, setKind] = useState<RunKind>('jobs')
  const [selected, setSelected] = useState<string[]>([])

  function selectKind(next: RunKind) {
    setKind(next)
    setSelected([])
  }

  function toggleSource(source: string, checked: boolean) {
    setSelected((prev) =>
      checked ? [...prev, source] : prev.filter((s) => s !== source)
    )
  }

  function start() {
    onStart(kind, selected)
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
            {SOURCES[kind].map((s) => (
              <label
                key={s}
                className="flex items-center gap-2 text-sm font-normal text-foreground"
              >
                <Checkbox
                  checked={selected.includes(s)}
                  onCheckedChange={(checked) => toggleSource(s, checked === true)}
                />
                {s}
              </label>
            ))}
          </div>
        </div>
        {SOURCES[kind].length === 0 && (
          <p className="text-xs text-muted-foreground">No sources for this kind yet.</p>
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
