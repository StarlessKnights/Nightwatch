import { useState } from 'react'
import type { Evidence, SourceRecord, ScenarioResult, ShiftBrief } from '../agentTypes'
import { money, eventText, compactNumber as n } from '../format'
import { OperatorDialog } from './OperatorDialog'
import { sourceNames, evidenceLabel } from '../evidenceFormat'
import { Handoff, ScenarioCompare } from './ShiftDesk'

type Obj = Record<string, unknown>
const object = (v: unknown): Obj => v !== null && typeof v === 'object' && !Array.isArray(v) ? v as Obj : {}
const labels: Record<string, string> = { volume: 'Stored volume', reported: 'Reported level', cap: 'Available capacity', eff_capacity_factor: 'Effective capacity', HH: 'High-high', time_to_HH: 'Time to high-high', time_to_H: 'Time to high', time_to_overflow: 'Time to overflow', ll_tripped: 'Low-low trip', tripped: 'High-high trip', do_nothing_cost: 'Cost with no new action', limited_by: 'Flow limited by', shared_capacity_assets: 'Other assets sharing capacity', transfer_supported: 'Buffer transfer available' }
const label = (s: string) => labels[s] ?? (s.charAt(0).toUpperCase() + s.slice(1)).replaceAll('_', ' ')
function scalar(k: string, v: unknown): string {
  if (v == null) return k.startsWith('time_to_') ? 'Not reached in forecast' : 'Not recorded'
  if (typeof v === 'boolean') return v ? 'Yes' : 'No'
  if (typeof v === 'number') {
    if (k.includes('cost') || ['total', 'fixed', 'hourly', 'production_loss', 'expected_consequence'].includes(k)) return money(v)
    if (k.includes('factor')) return n(100 * v) + '%'
    const suffix = /_pct$/.test(k) ? '%' : /^(volume|reported|capacity)$|_bbl$/.test(k) ? ' bbl' : /^(inflow|outflow|flow|rate|eff_rate|max_flow|max_intake|cap)$/.test(k) ? ' bbl/hr' : /_min$|^time_to_/.test(k) ? ' min' : ''
    return n(v) + suffix
  }
  return String(v).replaceAll('_', ' ')
}

function Fields({ value, name = '' }: { value: unknown; name?: string }) {
  const [expanded, expand] = useState(false)
  if (Array.isArray(value)) {
    if (!value.length) return <span className="hint">None</span>
    if (value.every(v => v == null || typeof v !== 'object')) return <div className="field-chips">{value.map((v,i) => <span key={i}>{scalar(name,v)}</span>)}</div>
    return <div>{value.slice(0, expanded ? undefined : 5).map((v,i) => <details key={i}><summary>{String(object(v).label ?? object(v).text ?? object(v).tank ?? (label(name) + ' ' + (i+1)))}</summary><Fields value={v} /></details>)}{value.length > 5 && <button onClick={() => expand(!expanded)}>{expanded ? 'Show fewer' : 'Show all ' + value.length}</button>}</div>
  }
  if (value === null || typeof value !== 'object') return <span>{scalar(name,value)}</span>
  return <dl className="field-list">{Object.entries(object(value)).map(([k,v]) => <div key={k}><dt>{label(k)}</dt><dd>{v !== null && typeof v === 'object' ? <details><summary>View {Array.isArray(v) ? v.length + ' items' : 'readings'}</summary><Fields value={v} name={k}/></details> : scalar(k,v)}</dd></div>)}</dl>
}

export function SourceTimeline({ rows }: { rows: SourceRecord[] }) {
  const [count, show] = useState(4)
  return <div className="source-timeline">{rows.slice(0,count).map(r => <article key={r.id}><time>T+{r.data.t_min}</time><div><span className="eyebrow">{r.data.tag} · {r.data.asset} · Run {r.run_id.slice(0,6)}</span><p>{eventText(r.data.text)}</p>
    <details><summary>Source record</summary><small>{r.data.text}<br/>Run {r.run_id}<br/>Record {r.id}<br/>Recorded {new Date(r.at).toLocaleString()}</small></details></div></article>)}
    {rows.length > count && <button onClick={() => show(count + 5)}>Show earlier records ({rows.length - count})</button>}</div>
}

function Meter({ title, value, max, unit }: { title: string; value: number; max: number; unit: string }) {
  return <div className="reading"><div><span>{title}</span><b>{n(value)} / {n(max)} {unit}</b></div><div className="read-track"><i style={{width: Math.min(100,Math.max(0,100 * value / max)) + '%'}}/></div></div>
}

function Forecast({ rows }: { rows: Obj[] }) {
  const milestones = [['time_to_H','High'],['time_to_HH','High-high'],['time_to_overflow','Overflow']]
  const scale = Math.max(1,...rows.flatMap(r => milestones.map(([k]) => typeof r[k] === 'number' ? Number(r[k]) : 0)))
  return <>{rows.map((r,i) => <article className="reading" key={i}><h4>{String(r.tank)} <small>· {String(r.status)}</small></h4>{milestones.map(([k,title]) => <div className="milestone" key={k}><span>{title}</span><div className="read-track">{typeof r[k] === 'number' && <i style={{width: Math.min(100,100 * r[k] / scale) + '%'}}/>}</div><b>{r[k] == null ? 'Not reached' : r[k] === 0 ? 'At limit' : n(Number(r[k])) + ' min'}</b></div>)}</article>)}<p className="hint">Times are measured from this observation. “Not reached” applies only to the forecast horizon.</p></>
}

function EvidenceBody({ e }: { e: Evidence }) {
  const v = object(e.value)
  if (e.source === 'get_shift_brief') return <Handoff brief={e.value as ShiftBrief}/>
  if (e.source === 'submit_scenario_proposal' && v.baseline) return <ScenarioCompare scenario={e.value as ScenarioResult}/>
  if (e.source === 'get_forecast' && (v.tank || Object.values(v).every(f => 'time_to_HH' in object(f)))) return <Forecast rows={v.tank ? [v] : Object.values(v).map(object)} />
  if (e.source === 'get_impact') return <>{[['upstream','Feeds this asset'],['downstream','Receives flow'],['shared_capacity_assets','Shares treatment capacity']].map(([key,title]) =>
    <div className="reading" key={key}><h4>{title}</h4><Fields value={v[key]} /></div>)}<p className="hint">These are network connections. Buffer transfers are not simulated.</p></>
  if (e.source === 'get_asset_state') {
    const capacity = typeof v.volume === 'number' && typeof v.capacity === 'number' ? <Meter title="Tank volume" value={v.volume} max={v.capacity} unit="bbl"/> : typeof v.eff_capacity_factor === 'number' ? <Meter title="Effective pump capacity" value={100 * v.eff_capacity_factor} max={100} unit="%" /> : typeof v.flow === 'number' && typeof v.cap === 'number' && v.cap > 0 ? <Meter title="Flow through asset" value={v.flow} max={v.cap} unit="bbl/hr" /> : null
    const keys = ['run_state','available','flow','eff_capacity_factor','inflow','outflow','reported','shut_in','curtailment_pct','limited_by']
    return <>{capacity}<div className="measure-grid">{keys.filter(k=> k in v).map(k=><div key={k}><small>{label(k)}</small><b>{scalar(k,v[k])}</b></div>)}</div><details><summary>All asset readings</summary><Fields value={v}/></details></>
  }
  if (Array.isArray(v.options) && 'do_nothing_cost' in v) {
    const ranked = Array.isArray(v.ranked_option_ids) ? v.ranked_option_ids : []
    return <><p>Cost with no new action <b>{money(Number(v.do_nothing_cost))}</b></p>
      {ranked.map((id,i) => { const opt = (v.options as Obj[]).find(o=> o.action_id === id); return opt && <div className="rank-line" key={String(id)}><small>#{i+1}</small><span>{String(opt.label)}</span><b>{money(object(opt.cost_breakdown).total as number|null)}</b></div> })}
      {!ranked.length && <p className="hint">No feasible action ranked.</p>}<details><summary>Options and assumptions</summary><Fields value={v}/></details></>
  }
  if (e.source === 'get_event_history' && 'data' in v) return <><p>{String(object(v.data).text ?? 'Recorded event')}</p><details><summary>Event details</summary><Fields value={v}/></details></>
  return <Fields value={e.value} name={e.path.split('.').at(-1)}/>
}

export function EvidenceViewer({ evidence: e, close }: { evidence: Evidence; close: () => void }) {
  return <OperatorDialog title="Simulator evidence" close={close}><span className="eyebrow">{sourceNames[e.source] ?? 'Simulator observation'} · T+{e.t_min}</span><h2>{evidenceLabel(e)}</h2><EvidenceBody e={e}/>
    <details className="provenance"><summary>Observation source</summary><dl className="field-list"><div><dt>Run</dt><dd>{e.run_id}</dd></div><div><dt>Revision</dt><dd>{e.revision}</dd></div><div><dt>Reading</dt><dd>{e.path}</dd></div></dl></details>
    <p className="hint">Recorded at T+{e.t_min}. Playback may have moved on.</p></OperatorDialog>
}
