import { useEffect, useState } from 'react'

import { apiUrl } from '../api/client'
import type { ApplicationDetail } from '../api/types'
import { useApi } from './useApi'

interface ApplicationLiveState {
  data: ApplicationDetail | null
  error: string | null
  reload: () => void
}

// Subscribes to GET /applications/{id}/stream (PHASE14.md step 5): the
// backend only sends a frame when this application's detail payload
// actually changed, replacing the drawer's old one-shot useApi fetch.
// Falls back to the existing poll (fallbackPollMs) whenever the SSE
// connection drops, so live updates degrade gracefully instead of going
// silent -- same shape as useRunsLive.ts. Reconnects whenever
// applicationId changes, since the drawer can be re-pointed at a
// different application without unmounting.
export function useApplicationLive(
  applicationId: number,
  fallbackPollMs: number | undefined,
): ApplicationLiveState {
  const [streamData, setStreamData] = useState<ApplicationDetail | null>(null)
  const [connected, setConnected] = useState(false)
  const fallback = useApi<ApplicationDetail>(
    `/applications/${applicationId}`,
    connected ? undefined : (fallbackPollMs ?? 5000),
  )

  useEffect(() => {
    setConnected(false)
    setStreamData(null)
    const source = new EventSource(apiUrl(`/applications/${applicationId}/stream`))
    source.onopen = () => setConnected(true)
    source.onmessage = (event: MessageEvent<string>) => {
      setConnected(true)
      setStreamData(JSON.parse(event.data) as ApplicationDetail)
    }
    source.onerror = () => setConnected(false)
    return () => source.close()
  }, [applicationId])

  return connected ? { data: streamData, error: null, reload: fallback.reload } : fallback
}
