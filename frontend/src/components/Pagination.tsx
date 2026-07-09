interface Props {
  offset: number
  limit: number
  total: number
  onOffset: (offset: number) => void
}

export function Pagination({ offset, limit, total, onOffset }: Props) {
  if (total <= limit) return null
  const page = Math.floor(offset / limit) + 1
  const pages = Math.ceil(total / limit)
  const buttonStyle =
    'rounded-lg border border-border px-3 py-1.5 text-sm text-muted-foreground ' +
    'hover:bg-muted disabled:opacity-40'
  return (
    <div className="flex items-center justify-between border-t border-border px-4 py-3">
      <span className="text-xs text-muted-foreground">
        Page {page} of {pages} · {total} total
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          className={buttonStyle}
          disabled={offset === 0}
          onClick={() => onOffset(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          type="button"
          className={buttonStyle}
          disabled={offset + limit >= total}
          onClick={() => onOffset(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  )
}
