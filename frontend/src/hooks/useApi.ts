import { useCallback, useEffect, useState } from 'react'

import { apiGet } from '../api/client'

interface ApiState<T> {
  data: T | null
  error: string | null
  reload: () => void
}

// Fetches a GET endpoint; re-fetches when the path changes, on reload(),
// and every `pollMs` when given (the dashboard polls while a run is active).
// path can be null to skip fetching entirely (e.g. a job drawer only
// fetching interview questions once its status is "interviewing",
// PHASE10.md step 9) — a real conditional fetch, not just a conditional
// render of already-fetched data.
export function useApi<T>(path: string | null, pollMs?: number): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tick, setTick] = useState(0)

  const reload = useCallback(() => setTick((n) => n + 1), [])

  useEffect(() => {
    if (path === null) return
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
