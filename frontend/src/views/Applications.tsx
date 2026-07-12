import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { Application, ApplicationDetail, Paginated, PlannedField } from '../api/types'
import { Drawer } from '../components/Drawer'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'

function statusBadgeVariant(status: string): 'outline' | 'secondary' | 'default' | 'destructive' {
  if (status === 'awaiting_confirmation') return 'default'
  if (status === 'submitted') return 'secondary'
  if (status === 'failed') return 'destructive'
  if (status === 'rejected') return 'outline'
  return 'outline'
}

function riskBadgeVariant(risk: string): 'outline' | 'secondary' | 'destructive' {
  return risk === 'high' ? 'destructive' : 'secondary'
}

function sourceBadgeVariant(source: string): 'outline' | 'secondary' | 'default' {
  if (source === 'profile') return 'secondary'
  if (source === 'llm') return 'default'
  return 'outline'
}

// The submission gate's own required record of "exactly what's about to
// happen" (PHASE11.md step 8) -- every planned field, the exact value
// that would be entered, and where it came from, shown before the one
// irreversible Confirm click.
function PlannedFieldRow({ field }: { field: PlannedField }) {
  return (
    <li className="flex items-start justify-between gap-3 py-2 text-sm">
      <div className="min-w-0">
        <p className="font-medium text-foreground">{field.label ?? field.field_name}</p>
        <p className="truncate text-muted-foreground">{field.answer ?? '(blank)'}</p>
      </div>
      <Badge variant={sourceBadgeVariant(field.source)}>{field.source}</Badge>
    </li>
  )
}

function ApplicationDrawer({
  application,
  onClose,
  onChanged,
}: {
  application: Application
  onClose: () => void
  onChanged: () => void
}) {
  const detail = useApi<ApplicationDetail>(`/applications/${application.id}`)
  const [busy, setBusy] = useState(false)

  async function confirm() {
    setBusy(true)
    try {
      await apiPost(`/applications/${application.id}/confirm`)
      toast.success('Confirmed -- submitting now')
      detail.reload()
      onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function reject() {
    setBusy(true)
    try {
      await apiPost(`/applications/${application.id}/reject`)
      toast.success('Rejected')
      detail.reload()
      onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const current = detail.data?.application ?? application

  return (
    <Drawer
      title={`${current.company_name}${current.job_title ? ` — ${current.job_title}` : ''}`}
      onClose={onClose}
    >
      <div className="mt-1 flex items-center gap-2 text-sm">
        <Badge variant={statusBadgeVariant(current.status)}>{current.status}</Badge>
        <Badge variant={riskBadgeVariant(current.risk_level)}>{current.risk_level} risk</Badge>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        started {formatTime(current.started_at)}
        {current.finished_at && ` · finished ${formatTime(current.finished_at)}`}
      </p>
      {current.error && <p className="mt-2 text-sm text-rose-600">{current.error}</p>}

      {current.status === 'awaiting_confirmation' && (
        <>
          <h3 className="mt-6 text-sm font-semibold text-foreground">Review before confirming</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Exactly what would be entered and submitted -- nothing is sent until you confirm.
          </p>
          <ul className="mt-2 divide-y divide-border">
            {current.planned_fields.map((field) => (
              <PlannedFieldRow key={field.field_name} field={field} />
            ))}
          </ul>
          <div className="mt-4 flex gap-2">
            <Button disabled={busy} onClick={() => void confirm()}>
              Confirm &amp; submit
            </Button>
            <Button variant="outline" disabled={busy} onClick={() => void reject()}>
              Reject
            </Button>
          </div>
        </>
      )}

      <h3 className="mt-6 text-sm font-semibold text-foreground">Event log</h3>
      <ul className="mt-2 divide-y divide-border text-sm">
        {(detail.data?.events ?? []).map((event) => (
          <li key={event.id} className="flex items-center justify-between py-1.5">
            <span className="text-foreground">{event.action}</span>
            <span className={event.success ? 'text-muted-foreground' : 'text-rose-600'}>
              {event.success ? 'ok' : (event.detail ?? 'failed')}
            </span>
          </li>
        ))}
      </ul>
    </Drawer>
  )
}

export function Applications() {
  const applications = useApi<Paginated<Application>>('/applications')
  const killSwitch = useApi<{ enabled: boolean }>('/autoapply/kill-switch')
  const [selected, setSelected] = useState<Application | null>(null)

  async function toggleKillSwitch() {
    try {
      await apiPost('/autoapply/kill-switch', { enabled: !killSwitch.data?.enabled })
      killSwitch.reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Applications</h1>
        <Button
          variant={killSwitch.data?.enabled ? 'destructive' : 'outline'}
          size="sm"
          onClick={() => void toggleKillSwitch()}
        >
          Kill switch: {killSwitch.data?.enabled ? 'ON' : 'off'}
        </Button>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        {applications.error && (
          <p className="px-4 py-3 text-sm text-rose-600">{applications.error}</p>
        )}
        <table className="w-full text-left text-sm">
          <thead className="bg-muted text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Job</th>
              <th className="px-4 py-2 font-medium">Status</th>
              <th className="px-4 py-2 font-medium">Risk</th>
              <th className="px-4 py-2 font-medium">Started</th>
            </tr>
          </thead>
          <tbody>
            {(applications.data?.items ?? []).map((application) => (
              <tr
                key={application.id}
                className="cursor-pointer border-t border-border hover:bg-indigo-50/40"
                onClick={() => setSelected(application)}
              >
                <td className="px-4 py-3 font-medium text-foreground">
                  {application.company_name}
                </td>
                <td className="px-4 py-3 text-muted-foreground">{application.job_title ?? '—'}</td>
                <td className="px-4 py-3">
                  <Badge variant={statusBadgeVariant(application.status)}>
                    {application.status}
                  </Badge>
                </td>
                <td className="px-4 py-3">
                  <Badge variant={riskBadgeVariant(application.risk_level)}>
                    {application.risk_level}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-muted-foreground">
                  {formatTime(application.started_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {applications.data?.items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-muted-foreground">
            No application attempts yet.
          </p>
        )}
      </div>

      {selected && (
        <ApplicationDrawer
          application={selected}
          onClose={() => setSelected(null)}
          onChanged={applications.reload}
        />
      )}
    </div>
  )
}
