import { useRef, useState } from 'react'
import { toast } from 'sonner'

import { apiGet, apiPost, apiUpload } from '../api/client'
import type { Job, Paginated, ResumeMarkdown, ResumePositions } from '../api/types'
import { Badge } from '../components/ui/badge'
import { Button } from '../components/ui/button'
import { Skeleton } from '../components/ui/skeleton'

// Upload a resume PDF, convert it to Markdown, derive job-search positions
// from its actual content, then let the user run a real hybrid search
// (PHASE6.md step 8's endpoint) for any derived position against already
// -scraped jobs (PHASE7.md step 4).
export function Resume() {
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [fileName, setFileName] = useState<string | null>(null)
  const [markdown, setMarkdown] = useState<string | null>(null)
  const [positions, setPositions] = useState<string[] | null>(null)
  const [converting, setConverting] = useState(false)
  const [deriving, setDeriving] = useState(false)
  const [selectedPosition, setSelectedPosition] = useState<string | null>(null)
  const [results, setResults] = useState<Job[] | null>(null)
  const [searching, setSearching] = useState(false)

  async function onFileSelected(file: File) {
    setFileName(file.name)
    setMarkdown(null)
    setPositions(null)
    setResults(null)
    setSelectedPosition(null)
    setConverting(true)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const { markdown: md } = await apiUpload<ResumeMarkdown>('/resume', formData)
      setMarkdown(md)
      setConverting(false)
      setDeriving(true)
      const { positions: derived } = await apiPost<ResumePositions>('/resume/positions', {
        markdown: md,
      })
      setPositions(derived)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setConverting(false)
      setDeriving(false)
    }
  }

  async function searchPosition(position: string) {
    setSelectedPosition(position)
    setSearching(true)
    setResults(null)
    try {
      const page = await apiGet<Paginated<Job>>(
        `/search?q=${encodeURIComponent(position)}&kind=jobs&limit=10`
      )
      setResults(page.items)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setSearching(false)
    }
  }

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-foreground">Resume</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Upload a resume PDF to find job titles worth searching for, based on its actual content.
      </p>

      <div className="mt-6 rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="sm" onClick={() => fileInputRef.current?.click()}>
            Choose PDF…
          </Button>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) void onFileSelected(file)
            }}
          />
          {fileName && <span className="text-sm text-muted-foreground">{fileName}</span>}
        </div>

        {converting && <Skeleton className="mt-4 h-24 w-full" />}

        {markdown && (
          <pre className="mt-4 max-h-64 overflow-auto rounded-lg bg-muted p-3 text-xs whitespace-pre-wrap text-muted-foreground">
            {markdown}
          </pre>
        )}

        {deriving && <Skeleton className="mt-4 h-8 w-64" />}

        {positions && (
          <div className="mt-4">
            <h2 className="text-sm font-semibold text-foreground">
              {positions.length > 0 ? 'Positions worth searching for' : 'No clear position found'}
            </h2>
            <div className="mt-2 flex flex-wrap gap-2">
              {positions.map((position) => (
                <button key={position} type="button" onClick={() => void searchPosition(position)}>
                  <Badge
                    variant={selectedPosition === position ? 'default' : 'secondary'}
                    className="cursor-pointer"
                  >
                    {position}
                  </Badge>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {selectedPosition && (
        <div className="mt-6 rounded-xl border border-border bg-card p-5">
          <h2 className="text-sm font-semibold text-foreground">
            Matching jobs for “{selectedPosition}”
          </h2>
          {searching && <Skeleton className="mt-3 h-20 w-full" />}
          {results && results.length === 0 && (
            <p className="mt-3 text-sm text-muted-foreground">No matching jobs scraped yet.</p>
          )}
          {results && results.length > 0 && (
            <ul className="mt-3 divide-y divide-border">
              {results.map((job) => (
                <li key={job.id} className="py-3">
                  <a
                    href={job.posting_url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-foreground hover:text-indigo-600"
                  >
                    {job.title}
                  </a>
                  <p className="text-sm text-muted-foreground">
                    {job.company}
                    {job.location && ` · ${job.location}`}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
