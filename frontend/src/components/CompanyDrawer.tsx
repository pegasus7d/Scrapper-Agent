import type { Company, Job, Paginated, Question } from '../api/types'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'
import { Badge } from './ui/badge'
import { Button } from './ui/button'
import { Drawer } from './Drawer'
import { Skeleton } from './ui/skeleton'

const SOURCE_LABELS: Record<string, string> = {
  yc: 'YC',
  largest_us_companies: 'Largest US companies',
  a16z: 'a16z',
  sequoia: 'Sequoia',
  foundersfund: 'Founders Fund',
  bvp: 'BVP',
}

export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source
}

export function ProviderBadge({ company }: { company: Company }) {
  if (company.ats_provider === null) {
    return <Badge variant="outline">unresolved</Badge>
  }
  return <Badge variant="secondary">{company.ats_provider}</Badge>
}

// The real payoff of phase 7's discovery/resolution/scraping: a company's
// own scraped jobs and any interview questions tagged with its name, both
// already real, filterable endpoints — no new backend needed for either
// (PHASE8.md step 1).
export function CompanyDrawer({
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
        <Badge variant="outline">{sourceLabel(company.source)}</Badge>
        {company.batch && <Badge variant="outline">{company.batch}</Badge>}
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
