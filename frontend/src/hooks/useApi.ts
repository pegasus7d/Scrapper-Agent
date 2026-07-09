import { useCallback, useEffect, useState } from 'react'

import { apiGet } from '../api/client'

interface ApiState<T> {
  data: T | null
  error: string | null
  reload: () => void
}

// Fetches a GET endpoint; re-fetches when the path changes, on reload(),
// and every `pollMs` when given (the dashboard polls while a run is active).
export function useApi<T>(path: string, pollMs?: number): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    let cancelled = false
    apiGet<T>(path)
      .then((result) => {
        if (!cancelled) {
          setData(result)
          setError(null)
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [path, tick])

  useEffect(() => {
    if (pollMs === undefined) return
    const id = setInterval(reload, pollMs)
    return () => clearInterval(id)
  }, [pollMs, reload])

  return { data, error, reload }
}
