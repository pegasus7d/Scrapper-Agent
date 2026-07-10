import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { Company, DiscoveryResult, Paginated, ResolutionResult, RunCreated } from '../api/types'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'

const inputStyle =
  'rounded-lg border border-border bg-card px-3 py-2 text-sm ' +
  'placeholder:text-muted-foreground focus:border-indigo-400 focus:outline-none'

function ProviderBadge({ company }: { company: Company }) {
  if (company.ats_provider === null) {
    return <Badge variant="outline">unresolved</Badge>
  }
  return <Badge variant="secondary">{company.ats_provider}</Badge>
}

// Discovered companies (PHASE7.md steps 5-7): scraped from ycombinator.com
// /companies, resolved against Greenhouse/Lever, then scraped as a real
// dynamic Source — no hand-curated company list anywhere in this flow.
export function Companies() {
  const [q, setQ] = useState('')
  const [discovering, setDiscovering] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [scrapingId, setScrapingId] = useState<number | null>(null)
  const companies = useApi<Paginated<Company>>('/companies')

  async function discover() {
    setDiscovering(true)
    try {
      const result = await apiPost<DiscoveryResult>('/companies/discover')
      toast.success(`Discovered ${result.discovered} new companies (${result.total} total)`)
      companies.reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setDiscovering(false)
    }
  }

  async function resolve() {
    setResolving(true)
    try {
      const result = await apiPost<ResolutionResult>('/companies/resolve')
      toast.success(`Resolved ${result.resolved} of ${result.checked} checked companies`)
      companies.reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setResolving(false)
    }
  }

  async function scrape(company: Company) {
    setScrapingId(company.id)
    try {
      const result = await apiPost<RunCreated>(`/companies/${company.id}/scrape`)
      toast.success(`Started run #${result.run_id} for ${company.name}`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setScrapingId(null)
    }
  }

  const items = companies.data?.items ?? []
  const filtered = q ? items.filter((c) => c.name.toLowerCase().includes(q.toLowerCase())) : items

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Companies</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className={inputStyle}
            placeholder="Filter by name…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <Button variant="outline" size="sm" disabled={discovering} onClick={() => void discover()}>
            {discovering ? 'Discovering…' : 'Discover companies'}
          </Button>
          <Button variant="outline" size="sm" disabled={resolving} onClick={() => void resolve()}>
            {resolving ? 'Resolving…' : 'Resolve companies'}
          </Button>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        {!companies.data && <Skeleton className="h-40 w-full" />}

        {companies.data && filtered.length === 0 && (
          <p className="p-6 text-sm text-muted-foreground">
            {items.length === 0
              ? 'No companies discovered yet — click "Discover companies" to scrape ycombinator.com/companies.'
              : 'No companies match that filter.'}
          </p>
        )}

        {filtered.length > 0 && (
          <ul className="divide-y divide-border">
            {filtered.map((company) => (
              <li key={company.id} className="flex items-center justify-between gap-4 p-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">{company.name}</span>
                    <ProviderBadge company={company} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    discovered {formatTime(company.discovered_at)}
                    {company.last_checked_at && ` · checked ${formatTime(company.last_checked_at)}`}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={company.ats_provider === null || scrapingId === company.id}
                  onClick={() => void scrape(company)}
                >
                  {scrapingId === company.id ? 'Starting…' : 'Scrape'}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
