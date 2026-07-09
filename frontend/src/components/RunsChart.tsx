import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { Run } from '../api/types'

interface Props {
  runs: Run[]
}

// recharts wants oldest-first for a left-to-right timeline; the API returns
// newest-first, so reverse and cap to the last 10 for a readable chart.
export function RunsChart({ runs }: Props) {
  const data = [...runs]
    .slice(0, 10)
    .reverse()
    .map((run) => ({
      label: `#${run.id}`,
      saved: run.items_saved,
      duplicates: run.items_duplicate,
    }))

  return (
    <div className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey="label" tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12, fill: 'var(--muted-foreground)' }} />
          <Tooltip
            contentStyle={{
              background: 'var(--popover)',
              border: '1px solid var(--border)',
              borderRadius: 'var(--radius)',
              fontSize: 12,
            }}
          />
          <Bar dataKey="saved" name="Saved" fill="var(--primary)" radius={[4, 4, 0, 0]} />
          <Bar
            dataKey="duplicates"
            name="Duplicates"
            fill="var(--muted-foreground)"
            radius={[4, 4, 0, 0]}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
