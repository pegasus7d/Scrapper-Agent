import { useState } from 'react'

import type { Paginated, Question } from '../api/types'
import { Drawer } from '../components/Drawer'
import { Pagination } from '../components/Pagination'
import { useApi } from '../hooks/useApi'
import { formatTime } from '../lib/format'

const LIMIT = 20

function questionsPath(q: string, company: string, round: string, offset: number): string {
  const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) })
  if (q) params.set('q', q)
  if (company) params.set('company', company)
  if (round) params.set('round', round)
  return `/questions?${params.toString()}`
}

function truncate(text: string, max = 90): string {
  return text.length <= max ? text : `${text.slice(0, max)}…`
}

function QuestionDrawer({ question, onClose }: { question: Question; onClose: () => void }) {
  return (
    <Drawer title={question.company} onClose={onClose}>
      <p className="mt-1 text-sm text-slate-500">
        {question.role ?? 'role unknown'}
        {question.round && ` · ${question.round}`}
      </p>
      <p className="mt-6 whitespace-pre-wrap text-sm leading-relaxed text-slate-700">
        {question.question}
      </p>
      <div className="mt-6 text-sm">
        <a
          className="font-medium text-indigo-600 hover:text-indigo-800"
          href={question.source_url}
          target="_blank"
          rel="noreferrer"
        >
          Source ↗
        </a>
      </div>
      <p className="mt-6 text-xs text-slate-400">
        {question.source} · {question.extraction_tier} tier · scraped{' '}
        {formatTime(question.scraped_at)}
      </p>
    </Drawer>
  )
}

const inputStyle =
  'rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm ' +
  'placeholder:text-slate-400 focus:border-indigo-400 focus:outline-none'

export function Questions() {
  const [q, setQ] = useState('')
  const [company, setCompany] = useState('')
  const [round, setRound] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, setSelected] = useState<Question | null>(null)
  const questions = useApi<Paginated<Question>>(questionsPath(q, company, round, offset))

  function updateFilter(setter: (value: string) => void) {
    return (value: string) => {
      setter(value)
      setOffset(0)
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Questions</h1>
        <div className="flex gap-2">
          <input
            className={inputStyle}
            placeholder="Search questions…"
            value={q}
            onChange={(e) => updateFilter(setQ)(e.target.value)}
          />
          <input
            className={inputStyle}
            placeholder="Company…"
            value={company}
            onChange={(e) => updateFilter(setCompany)(e.target.value)}
          />
          <input
            className={inputStyle}
            placeholder="Round…"
            value={round}
            onChange={(e) => updateFilter(setRound)(e.target.value)}
          />
        </div>
      </div>

      <div className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white">
        {questions.error && <p className="px-4 py-3 text-sm text-rose-600">{questions.error}</p>}
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-4 py-2 font-medium">Question</th>
              <th className="px-4 py-2 font-medium">Company</th>
              <th className="px-4 py-2 font-medium">Role</th>
              <th className="px-4 py-2 font-medium">Round</th>
              <th className="px-4 py-2 font-medium">Scraped</th>
            </tr>
          </thead>
          <tbody>
            {(questions.data?.items ?? []).map((question) => (
              <tr
                key={question.id}
                className="cursor-pointer border-t border-slate-100 hover:bg-indigo-50/40"
                onClick={() => setSelected(question)}
              >
                <td className="px-4 py-3 font-medium text-slate-900">
                  {truncate(question.question)}
                </td>
                <td className="px-4 py-3">{question.company}</td>
                <td className="px-4 py-3 text-slate-500">{question.role ?? '—'}</td>
                <td className="px-4 py-3 text-slate-500">{question.round ?? '—'}</td>
                <td className="px-4 py-3 text-slate-500">{formatTime(question.scraped_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {questions.data?.items.length === 0 && (
          <p className="px-4 py-8 text-center text-sm text-slate-400">No questions match.</p>
        )}
        {questions.data && (
          <Pagination
            offset={offset}
            limit={LIMIT}
            total={questions.data.total}
            onOffset={setOffset}
          />
        )}
      </div>

      {selected && <QuestionDrawer question={selected} onClose={() => setSelected(null)} />}
    </div>
  )
}
