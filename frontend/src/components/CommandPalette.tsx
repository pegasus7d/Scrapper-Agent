import { useEffect, useState } from 'react'

import { apiGet } from '../api/client'
import type { Job, Paginated } from '../api/types'
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

// Global ⌘K / Ctrl+K palette: switch views instantly, or search jobs by title
// and open the posting in a new tab (DESIGN.md §9 step 5).
export function CommandPalette({ onSelectView }: Props) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [jobs, setJobs] = useState<Job[]>([])

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
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      apiGet<Paginated<Job>>(`/jobs?q=${encodeURIComponent(query)}&limit=5`)
        .then((page) => {
          if (!cancelled) setJobs(page.items)
        })
        .catch(() => {
          if (!cancelled) setJobs([])
        })
    }, 200)
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

  function openJob(url: string) {
    window.open(url, '_blank', 'noreferrer')
    setOpen(false)
    setQuery('')
  }

  const matchingViews = VIEWS.filter((view) => view.includes(query.toLowerCase()))

  return (
    <CommandDialog open={open} onOpenChange={setOpen} title="Command palette">
      <Command shouldFilter={false}>
        <CommandInput
          placeholder="Switch views or search jobs…"
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
                <CommandItem key={job.id} onSelect={() => openJob(job.posting_url)}>
                  {job.title} — {job.company}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {query.trim().length >= 2 && matchingViews.length === 0 && jobs.length === 0 && (
            <CommandEmpty>No matches for “{query}”.</CommandEmpty>
          )}
        </CommandList>
      </Command>
    </CommandDialog>
  )
}
