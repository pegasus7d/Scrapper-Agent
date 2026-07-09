import { useState } from 'react'

import { CommandPalette } from './components/CommandPalette'
import { ThemeToggle } from './components/ThemeToggle'
import { Button } from './components/ui/button'
import { VIEWS, type View } from './lib/views'
import { Dashboard } from './views/Dashboard'
import { Jobs } from './views/Jobs'
import { Questions } from './views/Questions'
import { Resume } from './views/Resume'

function NavButton({
  view,
  active,
  onSelect,
}: {
  view: View
  active: boolean
  onSelect: (view: View) => void
}) {
  return (
    <Button
      type="button"
      variant={active ? 'secondary' : 'ghost'}
      className={`w-full justify-start px-3 py-2 text-left text-sm font-medium capitalize ${
        active ? 'text-indigo-700 dark:text-indigo-300' : 'text-muted-foreground'
      }`}
      onClick={() => onSelect(view)}
    >
      {view}
    </Button>
  )
}

export default function App() {
  const [view, setView] = useState<View>('dashboard')

  return (
    <div className="flex min-h-screen">
      <CommandPalette onSelectView={setView} />
      <aside className="flex w-56 flex-col gap-1 border-r border-border bg-card p-4">
        <div className="mb-6 flex items-center justify-between px-3 pt-2">
          <span className="text-lg font-bold tracking-tight text-foreground">
            Scraper<span className="text-indigo-600 dark:text-indigo-400"> Agent</span>
          </span>
          <ThemeToggle />
        </div>
        {VIEWS.map((v) => (
          <NavButton key={v} view={v} active={view === v} onSelect={setView} />
        ))}
        <p className="mt-auto px-3 pb-1 text-xs text-muted-foreground">
          <kbd className="rounded border border-border px-1 py-0.5 font-sans">⌘K</kbd> to search
        </p>
      </aside>
      <main className="flex-1">
        {view === 'dashboard' && <Dashboard />}
        {view === 'jobs' && <Jobs />}
        {view === 'questions' && <Questions />}
        {view === 'resume' && <Resume />}
      </main>
    </div>
  )
}
