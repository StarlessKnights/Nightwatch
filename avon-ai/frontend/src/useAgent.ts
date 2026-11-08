import { useCallback, useEffect, useState } from 'react'
import type { AgentState } from './agentTypes'

export async function agentCall<T = unknown>(path: string, body?: unknown): Promise<T> {
  const response = await fetch(`/api/agent${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail ?? 'Intelligence request failed')
  return data
}

export function useAgent(runId?: string) {
  const [data, setData] = useState<AgentState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    let disposed = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await agentCall<AgentState>('')
        if (!disposed && (!runId || next.run_id === runId)) { setData(next); setError(null) }
      } catch (e) { if (!disposed) setError(String(e)) }
      finally { if (!disposed) timer = window.setTimeout(poll, 1200) }
    }
    void poll()
    return () => { disposed = true; window.clearTimeout(timer) }
  }, [runId, refresh])
  const run = useCallback(async (path: string, body: unknown) => {
    try {
      setError(null)
      await agentCall(path, body)
      setRefresh((n) => n + 1)
      return true
    } catch (e) { setError(String(e)); return false }
  }, [])
  return { data: data && (!runId || data.run_id === runId) ? data : null, error, run }
}
