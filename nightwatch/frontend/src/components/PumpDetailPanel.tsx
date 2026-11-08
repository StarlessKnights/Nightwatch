import { useEffect, useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import type { AssetHistory, Curves, Envelope, Network } from '../types'
import { TimeSeriesStack } from './TimeSeriesStack'

const REFRESH_EVERY_MIN = 1 // sim minutes between refetches while open

function Curve({ curves, qmax }: { curves: Curves; qmax: number }) {
  const rows = curves.pump_curve.map((p, i) => ({
    Q: p.Q, pump: p.H, pumpH: curves.pump_curve_healthy[i].H, sys: curves.system_curve[i].H, sysH: curves.system_curve_healthy[i].H,
  }))
  return (
    <div>
      <div className="hint pad">Illustrative curves. Wear drops the pump curve; restriction steepens the system curve. The dot slides differently for each.</div>
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 18, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis dataKey="Q" type="number" domain={[0, qmax]} stroke="var(--muted)" tick={{ fontSize: 11 }}
            label={{ value: 'flow (kW)', position: 'insideBottom', offset: -10, fill: 'var(--muted)', fontSize: 11 }} />
          <YAxis stroke="var(--muted)" tick={{ fontSize: 11 }} width={40}
            label={{ value: 'head', angle: -90, position: 'insideLeft', fill: 'var(--muted)', fontSize: 11 }} />
          <Tooltip contentStyle={{ background: 'var(--panel)', border: '1px solid var(--border)' }} />
          <Line dataKey="pumpH" name="pump (healthy)" stroke="var(--flow)" strokeDasharray="5 4" strokeOpacity={0.5} dot={false} isAnimationActive={false} />
          <Line dataKey="sysH" name="system (healthy)" stroke="var(--warn)" strokeDasharray="5 4" strokeOpacity={0.5} dot={false} isAnimationActive={false} />
          <Line dataKey="pump" name="pump curve" stroke="var(--flow)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <Line dataKey="sys" name="system curve" stroke="var(--warn)" strokeWidth={2.5} dot={false} isAnimationActive={false} />
          <ReferenceDot x={curves.healthy_point.Q} y={curves.healthy_point.H} r={5} fill="none" stroke="var(--muted)" strokeDasharray="2 2" />
          <ReferenceDot x={curves.operating_point.Q} y={curves.operating_point.H} r={7} fill="var(--crit)" stroke="var(--text)" />
        </LineChart>
      </ResponsiveContainer>
      <div className="hint pad">
        <span style={{ color: 'var(--flow)' }}>━ pump</span> · <span style={{ color: 'var(--warn)' }}>━ system</span> · dashed = healthy ·
        ○ healthy point ({curves.healthy_point.Q.toFixed(0)}, {curves.healthy_point.H.toFixed(1)}) · ● operating point ({curves.operating_point.Q.toFixed(0)}, {curves.operating_point.H.toFixed(1)})
        {!curves.running && ' · pump not running (hypothetical point)'}
      </div>
    </div>
  )
}

export function PumpDetailPanel({ id, env, network, onClose }: { id: string; env: Envelope; network: Network; onClose: () => void }) {
  const [tab, setTab] = useState<'overview' | 'curves'>('overview')
  const [hist, setHist] = useState<AssetHistory | null>(null)
  const [curves, setCurves] = useState<Curves | null>(null)
  const pump = env.state.pumps[id]
  const tick = Math.floor(env.state.t_min / REFRESH_EVERY_MIN)
  const nFaults = env.state.faults.length
  const windowMin: number = network.config.history.buffer_min

  useEffect(() => {
    let live = true
    api.assetHistory(id, windowMin).then((h) => live && setHist(h)).catch(() => undefined)
    api.assetCurves(id).then((c) => live && setCurves(c)).catch(() => undefined)
    return () => { live = false }
  }, [id, tick, nFaults, windowMin, env.scenario.id])

  const d = pump.diagnosis
  const data = hist ? hist.series.t.map((t, i) => ({
    t: t as number, Q: hist.series.Q[i], expected: hist.expected_flow[i], P: hist.series.P[i],
  })) : []
  return (
    <div className="panel-fill scroll detail">
      <div className="panel-head">
        <h3>{id} detail</h3>
        <span className="chip">SIM</span>
        <span className={`chip ${pump.run_state === 'TRIPPED' ? 'crit' : ''}`}>{pump.available ? pump.run_state : 'UNAVAILABLE'}</span>
        <div className="spacer" />
        <button onClick={onClose}>✕ Close</button>
      </div>
      <div className="seg">
        <button className={tab === 'overview' ? 'on' : ''} onClick={() => setTab('overview')}>Overview</button>
        <button className={tab === 'curves' ? 'on' : ''} onClick={() => setTab('curves')}>Curves</button>
      </div>
      {tab === 'overview' && (
        <>
          <div className="diag">
            <div><b>{d?.text ?? '…'}</b></div>
            <div className="hint">w_est {d?.w_est?.toFixed(2) ?? '—'} · r_est {d?.r_est?.toFixed(2) ?? '—'} · flow {pump.Q.toFixed(0)} kW · P {pump.P.toFixed(1)}</div>
          </div>
          {hist && data.length > 0 ? (
            <TimeSeriesStack data={data} events={hist.events} startClock={network.config.ui.start_clock} height={150}
              panels={[
                { title: 'Flow', unit: 'kW', domain: [0, 'auto'], series: [{ key: 'Q', label: 'flow', color: 'var(--flow)' }, { key: 'expected', label: 'expected (healthy pump)', color: 'var(--muted)', dash: '4 4', faint: true }] },
                { title: 'Discharge pressure', unit: 'head', domain: [0, 'auto'], series: [{ key: 'P', label: 'pressure', color: 'var(--warn)' }] },
              ]} />
          ) : <div className="hint pad">Collecting samples…</div>}
        </>
      )}
      {tab === 'curves' && (curves ? <Curve curves={curves} qmax={network.config.pump_model.Qmax} /> : <div className="hint pad">Loading…</div>)}
    </div>
  )
}
