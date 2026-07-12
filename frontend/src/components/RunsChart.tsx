import type { Run } from '../api/types'

interface Props {
  runs: Run[]
}

// Fixed viewBox the SVG scales to fit its container — no resize-observer
// library needed (PHASE6.md step 5: dropped recharts, which cost ~351 KB,
// 42% of the bundle, for exactly this one grouped bar chart).
const WIDTH = 600
const HEIGHT = 220
const MARGIN = { top: 8, right: 8, bottom: 22, left: 28 }
const TICK_COUNT = 4

export function RunsChart({ runs }: Props) {
  // recharts wanted oldest-first for a left-to-right timeline; the API
  // returns newest-first, so reverse and cap to the last 10 for readability.
  const data = [...runs]
    .slice(0, 10)
    .reverse()
    .map((run) => ({
      label: `#${run.id}`,
      saved: run.items_saved,
      duplicates: run.items_duplicate,
    }))

  const innerWidth = WIDTH - MARGIN.left - MARGIN.right
  const innerHeight = HEIGHT - MARGIN.top - MARGIN.bottom
  const maxValue = Math.max(1, ...data.flatMap((d) => [d.saved, d.duplicates]))
  const groupWidth = innerWidth / Math.max(1, data.length)
  const barWidth = Math.max(2, groupWidth / 2 - 3)

  function barHeight(value: number): number {
    return (value / maxValue) * innerHeight
  }

  const ticks = Array.from({ length: TICK_COUNT + 1 }, (_, i) =>
    Math.round((maxValue / TICK_COUNT) * i),
  )

  return (
    <div className="h-56 w-full">
      <div className="mb-1 flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-sm bg-[var(--primary)]" /> Saved
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-sm bg-[var(--muted-foreground)]" /> Duplicates
        </span>
      </div>
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="h-[calc(100%-1.25rem)] w-full"
        role="img"
        aria-label="Items saved and duplicates per run"
      >
        <g transform={`translate(${MARGIN.left},${MARGIN.top})`}>
          {ticks.map((value) => {
            const y = innerHeight - barHeight(value)
            return (
              <g key={value}>
                <line
                  x1={0}
                  x2={innerWidth}
                  y1={y}
                  y2={y}
                  stroke="var(--border)"
                  strokeDasharray="3 3"
                />
                <text
                  x={-6}
                  y={y}
                  textAnchor="end"
                  dominantBaseline="middle"
                  fontSize={11}
                  fill="var(--muted-foreground)"
                >
                  {value}
                </text>
              </g>
            )
          })}
          {data.map((d, i) => {
            const groupX = i * groupWidth + (groupWidth - barWidth * 2) / 2
            return (
              <g key={d.label}>
                <rect
                  x={groupX}
                  y={innerHeight - barHeight(d.saved)}
                  width={barWidth}
                  height={barHeight(d.saved)}
                  fill="var(--primary)"
                  rx={2}
                >
                  <title>{`${d.label} — saved: ${d.saved}`}</title>
                </rect>
                <rect
                  x={groupX + barWidth}
                  y={innerHeight - barHeight(d.duplicates)}
                  width={barWidth}
                  height={barHeight(d.duplicates)}
                  fill="var(--muted-foreground)"
                  rx={2}
                >
                  <title>{`${d.label} — duplicates: ${d.duplicates}`}</title>
                </rect>
                <text
                  x={i * groupWidth + groupWidth / 2}
                  y={innerHeight + 15}
                  textAnchor="middle"
                  fontSize={11}
                  fill="var(--muted-foreground)"
                >
                  {d.label}
                </text>
              </g>
            )
          })}
        </g>
      </svg>
    </div>
  )
}
