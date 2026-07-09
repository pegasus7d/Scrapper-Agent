import { useEffect, useState } from 'react'

import { apiGet } from '../api/client'
import type { Job, Paginated, Question } from '../api/types'
import { VIEWS, type View } from '../lib/views'
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from './ui/command'

interface Props {
  onSelectView: (view: View) => void
}

// Global ⌘K / Ctrl+K palette: switch views instantly, or hybrid-search jobs
// and questions (PHASE2.md step 5, extended to GET /search in PHASE6.md
// step 8 — sqlite-vec similarity + FTS5 keyword, not a plain title substring
// match anymore) and open the result in a new tab.
export function CommandPalette({ onSelectView }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [jobs, setJobs] = useState<Job[]>([])
  const [questions, setQuestions] = useState<Question[]>([])

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key === 'k') {
        event.preventDefault()
        setOpen((prev) => !prev)
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  useEffect(() => {
    if (!open || query.trim().length < 2) {
      setJobs([])
      setQuestions([])
      return
    }
    let cancelled = false
    // A longer debounce than the old substring search: each query now
    // embeds via Ollama plus runs FTS5/vec0 queries, real work worth not
    // firing on every keystroke.
    const timer = setTimeout(() => {
      const params = `q=${encodeURIComponent(query)}&limit=5`
      apiGet<Paginated<Job>>(`/search?${params}&kind=jobs`)
        .then((page) => {
          if (!cancelled) setJobs(page.items)
        })
        .catch(() => {
          if (!cancelled) setJobs([])
        })
      apiGet<Paginated<Question>>(`/search?${params}&kind=questions`)
        .then((page) => {
          if (!cancelled) setQuestions(page.items)
        })
        .catch(() => {
          if (!cancelled) setQuestions([])
        })
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query, open])

  function selectView(view: View) {
    onSelectView(view)
    setOpen(false)
    setQuery('')
  }

  function openUrl(url: string) {
    window.open(url, '_blank', 'noreferrer')
    setOpen(false)
    setQuery('')
  }

  const matchingViews = VIEWS.filter((view) => view.includes(query.toLowerCase()))
  const noMatches =
    query.trim().length >= 2 &&
    matchingViews.length === 0 &&
    jobs.length === 0 &&
    questions.length === 0

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Command palette">
      <Command shouldFilter={false}>
        <CommandInput
          placeholder="Switch views or search jobs & questions…"
          value={query}
          onValueChange={setQuery}
        />
        <CommandList>
          {matchingViews.length > 0 && (
            <CommandGroup heading="Views">
              {matchingViews.map((view) => (
                <CommandItem key={view} onSelect={() => selectView(view)}>
                  {view}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {jobs.length > 0 && (
            <CommandGroup heading="Jobs">
              {jobs.map((job) => (
                <CommandItem key={job.id} onSelect={() => openUrl(job.posting_url)}>
                  {job.title} — {job.company}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {questions.length > 0 && (
            <CommandGroup heading="Questions">
              {questions.map((question) => (
                <CommandItem key={question.id} onSelect={() => openUrl(question.source_url)}>
                  {question.question}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {noMatches && <CommandEmpty>No matches for “{query}”.</CommandEmpty>}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
