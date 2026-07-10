import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type { Company, DiscoveryResult, Paginated, ResolutionResult, RunCreated } from '../api/types'
import { CompanyDrawer, ProviderBadge, sourceLabel } from '../components/CompanyDrawer'
import { Pagination } from '../components/Pagination'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Skeleton } from '../components/ui/skeleton'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'
import { COMPANY_DISCOVERY_SOURCES } from '../lib/sources'

const LIMIT = 20
const ALL_PROVIDERS = 'all'
const ALL_SOURCES = 'all'

const inputStyle =
  'rounded-lg border border-border bg-card px-3 py-2 text-sm ' +
  'placeholder:text-muted-foreground focus:border-indigo-400 focus:outline-none'

function companiesPath(q: string, atsProvider: string, source: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
  if (q) params.set('q', q)
  if (atsProvider !== ALL_PROVIDERS) params.set('ats_provider', atsProvider)
  if (source !== ALL_SOURCES) params.set('source', source)
  return `/companies?${params.toString()}`
}

// Discovered companies (PHASE7.md steps 5-7): scraped from ycombinator.com
// /companies, resolved against Greenhouse/Lever, then scraped as a real
// dynamic Source — no hand-curated company list anywhere in this flow.
export function Companies() {
  const [q, setQ] = useState('')
  const [atsProvider, setAtsProvider] = useState(ALL_PROVIDERS)
  const [source, setSource] = useState(ALL_SOURCES)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Company | null>(null)
  const [discoverySource, setDiscoverySource] = useState<string>(COMPANY_DISCOVERY_SOURCES[0])
  const [discovering, setDiscovering] = useState<string | null>(null)
  const [resolving, setResolving] = useState(false)
  const [scrapingId, setScrapingId] = useState<number | null>(null)
  const companies = useApi<Paginated<Company>>(companiesPath(q, atsProvider, source, offset))

  function updateFilter(setter: (value: string) => void) {
    return (value: string) => {
      setter(value)
      setOffset(0)
    }
  }

  async function discover(discoverySource: string) {
    setDiscovering(discoverySource)
    try {
      const result = await apiPost<DiscoveryResult>(
        `/companies/discover?source=${discoverySource}`
      )
      toast.success(`Discovered ${result.discovered} new companies (${result.total} total)`)
      companies.reload()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setDiscovering(null)
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
  const total = companies.data?.total ?? 0

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Companies</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            className={inputStyle}
            placeholder="Search names…"
            value={q}
            onChange={(e) => updateFilter(setQ)(e.target.value)}
          />
          <Select
            value={atsProvider}
            onValueChange={(value) => updateFilter(setAtsProvider)(value ?? ALL_PROVIDERS)}
          >
            <SelectTrigger className="w-40">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_PROVIDERS}>All providers</SelectItem>
              <SelectItem value="greenhouse">greenhouse</SelectItem>
              <SelectItem value="lever">lever</SelectItem>
            </SelectContent>
          </Select>
          <Select value={source} onValueChange={(value) => updateFilter(setSource)(value ?? ALL_SOURCES)}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_SOURCES}>All sources</SelectItem>
              {COMPANY_DISCOVERY_SOURCES.map((s) => (
                <SelectItem key={s} value={s}>
                  {sourceLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={discoverySource} onValueChange={(value) => setDiscoverySource(value ?? discoverySource)}>
            <SelectTrigger className="w-44">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {COMPANY_DISCOVERY_SOURCES.map((s) => (
                <SelectItem key={s} value={s}>
                  {sourceLabel(s)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            variant="outline"
            size="sm"
            disabled={discovering !== null}
            onClick={() => void discover(discoverySource)}
          >
            {discovering === discoverySource ? 'Discovering…' : `Discover ${sourceLabel(discoverySource)}`}
          </Button>
          <Button variant="outline" size="sm" disabled={resolving} onClick={() => void resolve()}>
            {resolving ? 'Resolving…' : 'Resolve companies'}
          </Button>
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-border bg-card">
        {!companies.data && <Skeleton className="h-40 w-full" />}

        {companies.data && items.length === 0 && (
          <p className="p-6 text-sm text-muted-foreground">
            {q || atsProvider !== ALL_PROVIDERS || source !== ALL_SOURCES
              ? 'No companies match those filters.'
              : 'No companies discovered yet — pick a source above and click "Discover" to scrape one.'}
          </p>
        )}

        {items.length > 0 && (
          <ul className="divide-y divide-border">
            {items.map((company) => (
              <li
                key={company.id}
                className="flex cursor-pointer items-center justify-between gap-4 p-4 hover:bg-indigo-50/40"
                onClick={() => setSelected(company)}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-foreground">{company.name}</span>
                    <ProviderBadge company={company} />
                    <Badge variant="outline">{sourceLabel(company.source)}</Badge>
                    {company.batch && <Badge variant="outline">{company.batch}</Badge>}
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
                  onClick={(e) => {
                    e.stopPropagation()
                    void scrape(company)
                  }}
                >
                  {scrapingId === company.id ? 'Starting…' : 'Scrape'}
                </Button>
              </li>
            ))}
          </ul>
        )}

        <Pagination offset={offset} limit={LIMIT} total={total} onOffset={setOffset} />
      </div>

      {selected && (
        <CompanyDrawer
          company={selected}
          scraping={scrapingId === selected.id}
          onScrape={() => void scrape(selected)}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
