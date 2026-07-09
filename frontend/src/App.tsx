import { useState } from 'react'

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
  const base = 'w-full rounded-lg px-3 py-2 text-left text-sm font-medium capitalize transition'
  const style = active
    ? 'bg-indigo-50 text-indigo-700'
    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
  return (
    <button type="button" className={`${base} ${style}`} onClick={() => onSelect(view)}>
      {view}
    </button>
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
