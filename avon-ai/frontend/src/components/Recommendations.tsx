import { useState } from 'react'
import { api } from '../api'
import { money, num } from '../format'
import type { Envelope, Option, Recommendation } from '../types'
import { PayoffBanner } from './PayoffBanner'

interface Props {
  env: Envelope; rec: Recommendation | null; selectedId: string | null
  onSelect: (id: string | null) => void; run: (fn: () => Promise<unknown>) => Promise<void>; disclaimer: string
}

function Cost({ o }: { o: Option }) {
  const c = o.cost_breakdown
  return (
    <div className="hint">
      fixed {money(c.fixed)} · running {money(c.hourly)} · compute service impact {money(c.production_loss)} · consequence {money(c.expected_consequence)}
    </div>
  )
}

export function Recommendations({ env, rec, selectedId, onSelect, run, disclaimer }: Props) {
  const [showRejected, setShowRejected] = useState(false)
  if (!rec) return <div className="panel-fill"><div className="hint pad">Computing…</div></div>
  const byId = new Map(rec.options.map((o) => [o.action_id, o]))
  const ranked = rec.ranked_option_ids.map((id) => byId.get(id)!)
  const dn = byId.get('DO_NOTHING')!
  const rejected = rec.options.filter((o) => !o.feasible && o.action_id !== 'DO_NOTHING')
  const advisoryOn = rec.engine_enabled

  return (
    <div className="panel-fill scroll">
      <div className="engine-title"><span className="eyebrow">Response options</span><h2>Decision Engine</h2><p className="hint">Compare responses to keep halls inside thermal limits. Costs and high-high forecasts are modeled; approvals apply to this simulation run. Assessed at T+{rec.as_of_min} min.</p></div>
      <div className={`headline st-${rec.status}`}>
        <span className="chip">{rec.status.toUpperCase()}</span>
        <span>{rec.headline}</span>
      </div>
      <PayoffBanner env={env} rec={rec} />
      {rec.probable_cause.length > 0 && (
        <div className="cause">
          <b>Probable cause</b>
          {rec.probable_cause.map((c, i) => <span key={i} className="chip">{c.asset} · {c.evidence_field} = {String(c.value)}</span>)}
          <div className="hint">
            upstream: {rec.affected_assets.upstream.join(', ') || '—'} · downstream: {rec.affected_assets.downstream.join(', ') || '—'}
            {rec.affected_assets.first_to_limit && <> · first to limit: <b>{rec.affected_assets.first_to_limit}</b></>}
          </div>
        </div>
      )}
      {advisoryOn && ranked.map((o, i) => (
        <div key={o.action_id} className={`opt ${selectedId === o.action_id ? 'sel' : ''}`} onClick={() => onSelect(selectedId === o.action_id ? null : o.action_id)}>
          {i === 0 && <div className="hint">Lowest modeled cost among feasible responses</div>}
          <div className="opt-top">
            <span className="rank">#{i + 1}</span>
            <b className="grow">{o.label}</b>
            <span className="cost"><small>Modeled cost</small>{money(o.cost_breakdown.total)}</span>
          </div>
          <Cost o={o} />
          <div className="response-timing"><span><small>Action deadline</small>{o.act_by_clock ?? 'No forecast deadline'}</span><span><small>Lead time</small>{o.lead_time_min} min</span><span><small>High-high margin</small>{num(o.margin_bbl, 0)} kWh</span></div>
          {o.trajectory_summary && <p className="response-outcome">{Object.values(o.trajectory_summary).every(tank => tank.time_to_HH === null) ? 'No high-high crossing modeled with this response.' : 'High-high crossing remains in the modeled forecast.'}</p>}
          {o.cost_breakdown.total != null && dn.cost_breakdown.total != null && <div className="hint">{dn.cost_breakdown.total >= o.cost_breakdown.total ? `${money(dn.cost_breakdown.total - o.cost_breakdown.total)} lower modeled cost than doing nothing` : `${money(o.cost_breakdown.total - dn.cost_breakdown.total)} higher modeled cost than doing nothing`}</div>}
          <button className="primary" onClick={(e) => { e.stopPropagation(); run(() => api.approve(o.action_id)) }}>Approve in simulation</button>
        </div>
      ))}
      {advisoryOn && ranked.length === 0 && rec.status !== 'normal' && <div className="hint pad">No feasible action found.</div>}
      <div className={`opt ref ${selectedId === 'DO_NOTHING' ? 'sel' : ''}`} onClick={() => onSelect(selectedId === 'DO_NOTHING' ? null : 'DO_NOTHING')}>
        <div className="opt-top"><span className="rank">ref</span><b className="grow">Do nothing</b><span className="cost">{money(dn.cost_breakdown.total)}</span></div>
        <div className="hint">{dn.feasible ? 'stays within limits' : dn.reasons.map((r) => r.text).join(' ')}</div>
      </div>
      {advisoryOn && rejected.length > 0 && (
        <>
          <button className="link" onClick={() => setShowRejected(!showRejected)}>{showRejected ? '▾' : '▸'} Rejected options ({rejected.length})</button>
          {showRejected && rejected.map((o) => (
            <div key={o.action_id} className="opt rejected">
              <div className="opt-top"><b className="grow">{o.label}</b><span className="cost">{o.cost_breakdown.total == null ? '' : money(o.cost_breakdown.total)}</span></div>
              {o.reasons.map((r) => <div key={r.code} className="reason"><span className="chip crit">{r.code}</span> {r.text}</div>)}
            </div>
          ))}
        </>
      )}
      <div className="disclaimer">{disclaimer}</div>
    </div>
  )
}
