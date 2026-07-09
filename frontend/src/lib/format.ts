// The backend stores naive UTC timestamps; mark them as UTC before display.
export function formatTime(iso: string): string {
  const utc = iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`
  return new Date(utc).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatPercent(fraction: number): string {
  return `${(fraction * 100).toFixed(1)}%`
}
