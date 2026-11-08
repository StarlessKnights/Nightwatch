import { useState } from 'react'
import type { AgentState, ScenarioResult, ShiftBrief, Trend } from '../agentTypes'
import { money, eventText, compactNumber as n } from '../format'


const signed = (v: number) => (v > 0 ? '+' : '') + n(v)
const toHH = (v: number | null) => v == null ? 'Not reached' : v === 0 ? 'Already at limit' : n(v) + ' min'

export function TrendChart({ trend }: { trend: Trend }) {
  const { samples } = trend
  if (samples.length < 2) return <p className="hint">One reading · {n(samples[0]?.bbl ?? 0)} kWh. Step or play to see change.</p>
  const lo = Math.min(...samples.map(p => p.bbl)), hi = Math.max(...samples.map(p => p.bbl))
  const first = samples[0], last = samples[samples.length - 1]
  const line = samples.map(p => (2 + 296 * (p.t - first.t) / (last.t - first.t || 1)) + ',' + (hi === lo ? 24 : 44 - 40 * (p.bbl - lo) / (hi - lo))).join(' ')
  return <figure className="trace"><svg role="img" aria-label={trend.tank + ': observed stored heat from ' + n(first.bbl) + ' to ' + n(last.bbl) + ' kWh'} viewBox="0 0 300 48" preserveAspectRatio="none">
    <path d="M0 44H300 M0 24H300 M0 4H300" stroke="var(--grid)" strokeDasharray="3 5" fill="none" />
    <polyline points={line} fill="none" stroke="var(--aqua)" strokeWidth="2" vectorEffect="non-scaling-stroke" />
  </svg><figcaption><span>T+{first.t} · {n(first.bbl)} kWh</span><span>T+{last.t} · {n(last.bbl)} kWh</span></figcaption></figure>
}

export function Handoff({ brief }: { brief: ShiftBrief }) {
  const [chosen, choose] = useState('')
  const trend = brief.trends.find(t => t.tank === chosen) ?? brief.trends[0]
  const limit = brief.first_limit
  return <div className="handoff">
    <span className="eyebrow">SHIFT HANDOFF · T+{brief.t_min}</span>
    <h2>{brief.unacknowledged ? brief.unacknowledged + (brief.unacknowledged === 1 ? ' alarm needs' : ' alarms need') + ' acknowledgment' : limit ? limit.tank + ' is first to the high-high limit' : 'No high-high crossing forecast'}</h2>
    <p className="hint">{limit ? limit.tank + ' · high-high level forecast at T+' + n(limit.at_min) : 'No hall reaches high-high in the ' + brief.horizon_min + '-minute forecast'}. Forecast from T+{brief.forecast_as_of}.</p>
    {trend && <div className="trend-block"><div className="section-line"><span className="eyebrow">Observed stored heat</span><select aria-label="Observed hall" value={trend.tank} onChange={e => choose(e.target.value)}>{brief.trends.map(t => <option key={t.tank}>{t.tank}</option>)}</select></div>
      <strong>{signed(trend.change_bbl)} <small>kWh</small></strong><TrendChart trend={trend} /></div>}
    <details className="brief-events"><summary>Recent changes · {brief.recent_events.length}</summary>
      {brief.recent_events.map(e => <p className="time-row" key={e.id}><time>T+{e.t_min}</time><span>{eventText(e.text)}</span></p>)}
      {!brief.recent_events.length && <p className="hint">No fault, alarm, operator or automatic events in the observed window.</p>}</details>
  </div>
}

export function ScenarioCompare({ scenario: s }: { scenario: ScenarioResult }) {
  const diff = s.do_nothing_cost - s.baseline.do_nothing_cost
  return <div className="comparison">
    <span className="eyebrow">ISOLATED FORECAST · T+{s.t_min}</span>
    <h4>{s.faults.map(f => f.target + ' · ' + f.type.toLowerCase().replaceAll('_', ' ') + (typeof f.params.factor === 'number' ? ' (' + n(100 * f.params.factor) + '% capacity)' : '')).join(' + ')}</h4>
    <table><caption>Time to high-high · {s.horizon_min}-minute horizon</caption><thead><tr><th>Hall / storage</th><th>As observed</th><th>With fault</th></tr></thead><tbody>{Object.entries(s.forecast).map(([tank, f]) => <tr key={tank}><th>{tank}</th><td>{toHH(s.baseline.forecast[tank].time_to_HH)}</td><td>{toHH(f.time_to_HH)}</td></tr>)}</tbody></table>
    <p>Do-nothing cost: {money(s.baseline.do_nothing_cost)} → <b>{money(s.do_nothing_cost)}</b></p>
    <p className="hint">{diff === 0 ? 'No change in modeled cost.' : money(Math.abs(diff)) + (diff > 0 ? ' higher' : ' lower') + ' with the hypothetical fault.'}</p>
  </div>
}

export function ShiftDesk({ data, openIncidents, openLab }: { data: AgentState; openIncidents: () => void; openLab: () => void }) {
  const active = data.incidents.filter(i => i.status === 'active')
  return <>{data.shift_brief ? <Handoff brief={data.shift_brief} /> : <p className="agent-notice">Enable monitoring to see the current shift handoff.</p>}
    {active.length > 0 && <button className="case-link" onClick={openIncidents}>Investigate {active.length} open {active.length === 1 ? 'incident' : 'incidents'} ↗</button>}
    <button className="case-link" onClick={openLab}>Compare a hypothetical disruption ↗</button></>
}

export function WhatIfLab({ data, run, openEvidence }: { data: AgentState; run: (path: string, body: unknown) => Promise<boolean>; openEvidence: (id: string) => void }) {
  const [choice, setChoice] = useState('standby'), [running, setRunning] = useState(false)
  const latest = data.scenarios.at(-1)
  return <div className="lab"><span className="eyebrow">WHAT-IF LAB</span><h4>Compare a disruption</h4><p className="hint">See how a fault changes hall limits and cost. Playback is unaffected.</p>
      <form onSubmit={async e => { e.preventDefault(); setRunning(true); try { await run('/scenarios', { faults: [choice === 'standby' ? { type: 'PUMP_UNAVAILABLE', target: 'CHP-2' } : { type: 'TREATMENT_CONSTRAINT', target: 'HRJ-1', params: { factor: 0.5 } }] }) } finally { setRunning(false) } }}>
      <select aria-label="Hypothetical disruption" value={choice} onChange={e => setChoice(e.target.value)}><option value="standby">CHP-2 standby unavailable</option><option value="treatment">Heat rejection at 50% capacity</option></select>
      <button disabled={running || !data.enabled}>{running ? 'Comparing…' : 'Compare'}</button></form>
      {latest && <><ScenarioCompare scenario={latest} /><button className="link-inline" onClick={() => openEvidence(latest.evidence_ids[0])}>View recorded comparison ↗</button></>}
    </div>
}
