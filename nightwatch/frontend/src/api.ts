import type { AssetHistory, Curves, Json, Network, PumpDiagnosis, Recommendation } from './types'

async function call<T = Json>(method: string, url: string, body?: unknown): Promise<T> {
  const r = await fetch(url, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (!r.ok) throw new Error(`${r.status} ${(await r.json().catch(() => ({}))).detail ?? r.statusText}`)
  return r.json()
}

export const api = {
  network: () => call<Network & { snapshot: Json }>('GET', '/api/network'),
  recommendation: () => call<Recommendation>('GET', '/api/recommendation'),
  start: () => call('POST', '/api/sim/start'),
  pause: () => call('POST', '/api/sim/pause'),
  step: () => call('POST', '/api/sim/step'),
  reset: () => call('POST', '/api/sim/reset'),
  speed: (x: number) => call('POST', '/api/sim/speed', { x }),
  engine: (enabled: boolean) => call('POST', '/api/sim/engine', { enabled }),
  loadScenario: (id: string) => call('POST', `/api/scenarios/${id}/load`),
  injectFault: (type: string, target: string, params: Json) => call('POST', '/api/faults', { type, target, params }),
  clearFault: (id: string) => call('DELETE', `/api/faults/${id}`),
  approve: (optionId: string, runId: string) => call('POST', `/api/recommendation/${encodeURIComponent(optionId)}/approve?run_id=${encodeURIComponent(runId)}`),
  ack: (id: string) => call('POST', `/api/alarms/${encodeURIComponent(id)}/ack`),
  patchConfig: (patch: Json) => call('PATCH', '/api/config', patch),
  assetHistory: (id: string, windowMin: number) => call<AssetHistory>('GET', `/api/assets/${id}/history?window_min=${windowMin}`),
  assetCurves: (id: string) => call<Curves>('GET', `/api/assets/${id}/curves`),
  assetDiagnosis: (id: string) => call<PumpDiagnosis>('GET', `/api/assets/${id}/diagnosis`),
  impact: (id: string) => call<{ upstream: string[]; downstream: string[]; first_to_limit: string | null }>('GET', `/api/impact/${id}`),
}
