import { useEffect, useState } from 'react'

import { apiUrl } from '../api/client'
import type { Paginated, Run } from '../api/types'
import { useApi } from './useApi'

interface RunsLiveState {
  data: Paginated<Run> | null
  error: string | null
  reload: () => void
}

// Subscribes to GET /runs/stream (PHASE6.md step 6): the backend only sends
// a frame when the runs list actually changed, replacing the dashboard's
// old fixed-interval poll-while-active. Falls back to the existing poll
// (fallbackPollMs) whenever the SSE connection drops, so live updates
// degrade gracefully instead of going silent.
export function useRunsLive(fallbackPollMs: number | undefined): RunsLiveState {
  const [streamData, setStreamData] = useState<Paginated<Run> | null>(null)
  const [connected, setConnected] = useState(false)
  const fallback = useApi<Paginated<Run>>('/runs', connected ? undefined : (fallbackPollMs ?? 5000))

  useEffect(() => {
    const source = new EventSource(apiUrl('/runs/stream'))
    source.onopen = () => setConnected(true)
    source.onmessage = (event: MessageEvent<string>) => {
      setConnected(true)
      setStreamData(JSON.parse(event.data) as Paginated<Run>)
    }
    source.onerror = () => setConnected(false)
    return () => source.close()
  }, [])

  return connected ? { data: streamData, error: null, reload: fallback.reload } : fallback
}
