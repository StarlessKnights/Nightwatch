import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from './api'
import type { Envelope, HistoryPoint, Network, Recommendation, SimEvent } from './types'

export interface SimData {
  network: Network | null
  env: Envelope | null
  history: HistoryPoint[]
  events: SimEvent[]
  rec: Recommendation | null
  connected: boolean
  refreshRec: () => void
  error: string | null
  run: (fn: () => Promise<unknown>) => Promise<void>
}

const RECONNECT_MS = 1000
const REC_MIN_INTERVAL_MS = 1500
const EVENT_CAP = 2000

export function useSim(): SimData {
  const [network, setNetwork] = useState<Network | null>(null)
  const [env, setEnv] = useState<Envelope | null>(null)
  const [history, setHistory] = useState<HistoryPoint[]>([])
  const [events, setEvents] = useState<SimEvent[]>([])
  const [rec, setRec] = useState<Recommendation | null>(null)
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const historyCap = useRef(720)
  const lastFetch = useRef(0)
  const timer = useRef<number | undefined>(undefined)

  const refreshRec = useCallback(() => {
    window.clearTimeout(timer.current)
    const wait = Math.max(0, lastFetch.current + REC_MIN_INTERVAL_MS - Date.now())
    timer.current = window.setTimeout(() => {
      lastFetch.current = Date.now()
      api.recommendation().then(setRec).catch(() => undefined)
    }, wait)
  }, [])

  const apply = useCallback((msg: any) => {
    const { type, history: h, new_events, event_log, ...rest } = msg
    setEnv(rest as Envelope)
    if (type === 'sync') {
      setHistory(h)
      setEvents(event_log)
    } else {
      if (h?.length) setHistory((p) => [...p, ...h].slice(-historyCap.current))
      if (new_events?.length) setEvents((p) => [...p, ...new_events].slice(-EVENT_CAP))
    }
  }, [])

  useEffect(() => {
    api.network().then((n) => {
      historyCap.current = n.config.ui.history_points
      setNetwork(n)
      apply(n.snapshot)
    }).catch((e) => setError(String(e)))
  }, [apply])

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let retry: number | undefined
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/sim`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => apply(JSON.parse(e.data))
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = window.setTimeout(connect, RECONNECT_MS) // tolerate reconnects
      }
    }
    connect()
    return () => { closed = true; window.clearTimeout(retry); ws?.close() }
  }, [apply])

  const sig = env ? `${env.state.t_min}|${env.state.faults.length}|${env.state.pending_actions.length}|${env.engine_enabled}|${env.auto_changeover_on_low_flow}|${env.scenario.id}` : ''
  useEffect(() => { if (sig) refreshRec() }, [sig, refreshRec])

  const run = useCallback(async (fn: () => Promise<unknown>) => {
    try { setError(null); await fn() } catch (e) { setError(String(e)) }
    refreshRec()
  }, [refreshRec])

  return { network, env, history, events, rec, connected, refreshRec, error, run }
}
