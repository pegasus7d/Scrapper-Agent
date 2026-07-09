import type { Run } from '../api/types'
import { Badge } from './ui/badge'

interface Props {
  run: Run
}

// Live detail card for the one run that can currently be "running" — the
// dashboard's stat cards and table already poll every 3s, this just surfaces
// the same numbers up close, plus the most recent errors as they land.
export function RunProgressPanel({ run }: Props) {
  const recentErrors = run.errors.slice(-3).reverse()

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
        </div>
        <Badge variant="secondary">running</Badge>
      </div>

      <dl className="mt-4 grid grid-cols-4 gap-4 text-center">
        <div>
          <dt className="text-xs text-muted-foreground">Pages</dt>
          <dd className="text-lg font-semibold text-foreground">{run.pages_fetched}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Saved</dt>
          <dd className="text-lg font-semibold text-foreground">{run.items_saved}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Duplicates</dt>
          <dd className="text-lg font-semibold text-foreground">{run.items_duplicate}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Errors</dt>
          <dd className="text-lg font-semibold text-foreground">{run.errors.length}</dd>
        </div>
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
