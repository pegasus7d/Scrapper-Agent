import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { RunCreated, RunKind } from '../api/types'
import { SOURCES } from '../lib/sources'
import { Button } from './ui/button'
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
  onStarted: () => void
}

export function NewScrapeModal({ onClose, onStarted }: Props) {
  const [kind, setKind] = useState<RunKind>('jobs')
  const [source, setSource] = useState(SOURCES.jobs[0] ?? '')
  const [busy, setBusy] = useState(false)

  function selectKind(next: RunKind) {
    setKind(next)
    setSource(SOURCES[next][0] ?? '')
  }

  async function start() {
    setBusy(true)
    try {
      await apiPost<RunCreated>('/runs', { kind, source })
      toast.success(`Started ${kind} scrape from ${source}`)
      onStarted()
      onClose()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
      setBusy(false)
    }
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

        <label className="block text-sm font-medium text-muted-foreground">
          Source
          <Select value={source} onValueChange={(v) => setSource(v ?? '')}>
            <SelectTrigger className="mt-1 w-full">
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
        </label>
        {SOURCES[kind].length === 0 && (
          <p className="text-xs text-muted-foreground">No sources for this kind yet.</p>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button disabled={busy || source === ''} onClick={() => void start()}>
            Start
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
