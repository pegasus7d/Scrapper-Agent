import { useState } from 'react'

import { Button } from './components/ui/button'
import { Dashboard } from './views/Dashboard'
import { Jobs } from './views/Jobs'
import { Questions } from './views/Questions'

const VIEWS = ['dashboard', 'jobs', 'questions'] as const
type View = (typeof VIEWS)[number]

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
        active ? 'text-indigo-700' : 'text-slate-600'
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
      <aside className="flex w-56 flex-col gap-1 border-r border-slate-200 bg-white p-4">
        <div className="mb-6 px-3 pt-2">
          <span className="text-lg font-bold tracking-tight text-slate-900">
            Scraper<span className="text-indigo-600"> Agent</span>
          </span>
        </div>
        {VIEWS.map((v) => (
          <NavButton key={v} view={v} active={view === v} onSelect={setView} />
        ))}
      </aside>
      <main className="flex-1">
        {view === 'dashboard' && <Dashboard />}
        {view === 'jobs' && <Jobs />}
        {view === 'questions' && <Questions />}
      </main>
    </div>
  )
}
