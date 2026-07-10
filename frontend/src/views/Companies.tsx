import { useState } from 'react'
import { toast } from 'sonner'

import { apiPost } from '../api/client'
import type {
  Company,
  DiscoveryResult,
  Job,
  Paginated,
  Question,
  ResolutionResult,
  RunCreated,
} from '../api/types'
import { Drawer } from '../components/Drawer'
import { Pagination } from '../components/Pagination'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select'
import { Skeleton } from '../components/ui/skeleton'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'

const LIMIT = 20
const ALL_PROVIDERS = 'all'

const inputStyle =
  'rounded-lg border border-border bg-card px-3 py-2 text-sm ' +
  'placeholder:text-muted-foreground focus:border-indigo-400 focus:outline-none'

function companiesPath(q: string, atsProvider: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
  if (q) params.set('q', q)
  if (atsProvider !== ALL_PROVIDERS) params.set('ats_provider', atsProvider)
  return `/companies?${params.toString()}`
}

function ProviderBadge({ company }: { company: Company }) {
  if (company.ats_provider === null) {
    return <Badge variant="outline">unresolved</Badge>
  }
  return <Badge variant="secondary">{company.ats_provider}</Badge>
}

// The real payoff of phase 7's discovery/resolution/scraping: a company's
// own scraped jobs and any interview questions tagged with its name, both
// already real, filterable endpoints — no new backend needed for either
// (PHASE8.md step 1).
function CompanyDrawer({
  company,
  scraping,
  onScrape,
  onClose,
}: {
  company: Company
  scraping: boolean
  onScrape: () => void
  onClose: () => void
}) {
  const jobs = useApi<Paginated<Job>>(
    `/jobs?source=company:${company.slug ?? 'unresolved'}&limit=10`
  )
  const questions = useApi<Paginated<Question>>(
    `/questions?company=${encodeURIComponent(company.name)}&limit=10`
  )

  return (
    <Drawer title={company.name} onClose={onClose}>
      <div className="flex items-center gap-2">
        <ProviderBadge company={company} />
        {company.slug && <span className="text-sm text-muted-foreground">{company.slug}</span>}
        {company.batch && <Badge variant="outline">YC {company.batch}</Badge>}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        discovered {formatTime(company.discovered_at)}
        {company.last_checked_at && ` · checked ${formatTime(company.last_checked_at)}`}
      </p>
      <Button
        className="mt-4"
        variant="outline"
        size="sm"
        disabled={company.ats_provider === null || scraping}
        onClick={onScrape}
      >
        {scraping ? 'Starting…' : 'Scrape this company'}
      </Button>

      <h3 className="mt-6 text-sm font-semibold text-foreground">Scraped jobs</h3>
      {!company.slug && (
        <p className="mt-2 text-sm text-muted-foreground">Not resolved to an ATS yet.</p>
      )}
      {company.slug && !jobs.data && <Skeleton className="mt-2 h-16 w-full" />}
      {company.slug && jobs.data && jobs.data.items.length === 0 && (
        <p className="mt-2 text-sm text-muted-foreground">No jobs scraped from here yet.</p>
      )}
      {jobs.data && jobs.data.items.length > 0 && (
        <ul className="mt-2 space-y-2">
          {jobs.data.items.map((job) => (
            <li key={job.id} className="text-sm">
              <a
                href={job.posting_url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-indigo-600 hover:text-indigo-800"
              >
                {job.title}
              </a>
              {job.location && <span className="text-muted-foreground"> · {job.location}</span>}
            </li>
          ))}
        </ul>
      )}

      <h3 className="mt-6 text-sm font-semibold text-foreground">Interview questions</h3>
      {!questions.data && <Skeleton className="mt-2 h-16 w-full" />}
      {questions.data && questions.data.items.length === 0 && (
        <p className="mt-2 text-sm text-muted-foreground">No questions reported yet.</p>
      )}
      {questions.data && questions.data.items.length > 0 && (
        <ul className="mt-2 space-y-2">
          {questions.data.items.map((question) => (
            <li key={question.id} className="text-sm text-foreground">
              {question.question}
              {question.round && <span className="text-muted-foreground"> — {question.round}</span>}
            </li>
          ))}
        </ul>
      )}
    </Drawer>
  )
}

// Discovered companies (PHASE7.md steps 5-7): scraped from ycombinator.com
// /companies, resolved against Greenhouse/Lever, then scraped as a real
// dynamic Source — no hand-curated company list anywhere in this flow.
export function Companies() {
  const [q, setQ] = useState('')
  const [atsProvider, setAtsProvider] = useState(ALL_PROVIDERS)
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Company | null>(null)
  const [discovering, setDiscovering] = useState(false)
  const [resolving, setResolving] = useState(false)
  const [scrapingId, setScrapingId] = useState<number | null>(null)
  const companies = useApi<Paginated<Company>>(companiesPath(q, atsProvider, offset))

  function updateFilter(setter: (value: string) => void) {
    return (value: string) => {
      setter(value)
      setOffset(0)
    }
  }

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

        {companies.data && items.length === 0 && (
          <p className="p-6 text-sm text-muted-foreground">
            {q || atsProvider !== ALL_PROVIDERS
              ? 'No companies match those filters.'
              : 'No companies discovered yet — click "Discover companies" to scrape ycombinator.com/companies.'}
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
                    {company.batch && <Badge variant="outline">YC {company.batch}</Badge>}
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
