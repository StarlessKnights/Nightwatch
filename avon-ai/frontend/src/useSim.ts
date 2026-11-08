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
  const latestRun = useRef('')
  const requestNumber = useRef(0)
  const receivedSocketState = useRef(false)

  const refreshRec = useCallback(() => {
    window.clearTimeout(timer.current)
    const wait = Math.max(0, lastFetch.current + REC_MIN_INTERVAL_MS - Date.now())
    timer.current = window.setTimeout(() => {
      lastFetch.current = Date.now()
      const request = ++requestNumber.current
      api.recommendation().then(next => {
        if (request === requestNumber.current && next.run_id === latestRun.current) setRec(next)
      }).catch(e => { if (request === requestNumber.current) setError(String(e)) })
    }, wait)
  }, [])

  const apply = useCallback((msg: any) => {
    const { type, history: h, new_events, event_log, ...rest } = msg
    if (latestRun.current !== rest.state.run_id) {
      latestRun.current = rest.state.run_id
      ++requestNumber.current
      setRec(null)
    }
    setEnv(rest as Envelope)
    if (type === 'sync') {
      setHistory(h)
      setEvents(event_log)
    } else {
      if (h?.length) setHistory((p) => [...p, ...h.filter((point: HistoryPoint) => point.t > (p.at(-1)?.t ?? -1))].slice(-historyCap.current))
      if (new_events?.length) setEvents((p) => [...p, ...new_events.filter((e: SimEvent) => e.id > (p.at(-1)?.id ?? -1))].slice(-EVENT_CAP))
    }
  }, [])

  useEffect(() => {
    let active = true
    let retry: number | undefined
    const load = () => api.network().then((n) => {
      if (!active) return
      historyCap.current = n.config.ui.history_points
      setNetwork(n)
      setError(null)
      if (!receivedSocketState.current) apply(n.snapshot)
    }).catch((e) => { if (active) { setError(String(e)); retry = window.setTimeout(load, RECONNECT_MS) } })
    void load()
    return () => { active = false; window.clearTimeout(retry); window.clearTimeout(timer.current); ++requestNumber.current }
  }, [apply])

  useEffect(() => {
    let ws: WebSocket | null = null
    let closed = false
    let retry: number | undefined
    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/sim`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => { if (!closed) { receivedSocketState.current = true; apply(JSON.parse(e.data)) } }
      ws.onclose = () => {
        setConnected(false)
        if (!closed) retry = window.setTimeout(connect, RECONNECT_MS) // tolerate reconnects
      }
    }
    connect()
    return () => { closed = true; window.clearTimeout(retry); ws?.close() }
  }, [apply])

  const sig = env ? `${env.state.run_id}|${env.state.t_min}|${env.state.faults.length}|${env.state.pending_actions.length}|${env.engine_enabled}|${env.auto_changeover_on_low_flow}|${env.scenario.id}` : ''
  useEffect(() => { if (sig) refreshRec() }, [sig, refreshRec])

  const run = useCallback(async (fn: () => Promise<unknown>) => {
    try { setError(null); await fn() } catch (e) { setError(String(e)) }
    refreshRec()
  }, [refreshRec])

  return { network, env, history, events, rec, connected, refreshRec, error, run }
}
