import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { clock } from '../format'
import type { Envelope, HistoryPoint, Network, Option, Recommendation } from '../types'

interface Props { visible?: boolean; env: Envelope; network: Network; history: HistoryPoint[]; rec: Recommendation | null; selected: Option | null }

export function TankTrends({ env, network, history, rec, selected, visible = true }: Props) {
  const tanks = Object.keys(env.state.tanks).filter((t) => !env.state.tanks[t].role)
  const [tank, setTank] = useState(tanks[0])
  const lim = network.config.limits
  const cap = env.state.tanks[tank].capacity
  const step = env.forecast.series_step_min
  const t0 = env.forecast.as_of_min
  const startClock = network.config.ui.start_clock

  const rows = new Map<number, Record<string, number>>()
  const put = (t: number, k: string, v: number) => rows.set(t, { ...(rows.get(t) ?? { t }), [k]: v })
  history.forEach((p) => put(p.t, 'history', p[tank]))
  env.forecast.tanks[tank]?.series.forEach((v, i) => put(t0 + i * step, 'forecast', v))
  env.forecast.do_nothing?.[tank]?.forEach((v, i) => put(t0 + i * step, 'noaction', v))
  const sel = selected?.trajectory_summary?.[tank]
  sel?.series.forEach((v, i) => put((rec ? rec.as_of_min : t0) + i * step, 'option', v))
  const data = [...rows.values()].sort((a, b) => a.t - b.t)
  const actBy = selected?.act_by_min ?? null

  return (
    <div className="panel-fill">
      <div className="panel-head">
        <h3>Tank trends</h3>
        <div className="seg">{tanks.map((t) => <button key={t} className={t === tank ? 'on' : ''} onClick={() => setTank(t)}>{t}</button>)}</div>
        <div className="legend">
          <span style={{ color: 'var(--flow)' }}>━ history</span> <span style={{ color: 'var(--warn)' }}>┅ forecast (as-is)</span>
          {env.forecast.do_nothing && <span style={{ color: 'var(--crit)' }}> ┅ without approved actions</span>}
          {selected && <span style={{ color: 'var(--ok)' }}> ┅ with “{selected.label}”</span>}
        </div>
      </div>
      {visible && <ResponsiveContainer width="100%" height="85%">
        <LineChart data={data} margin={{ top: 8, right: 24, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="var(--grid)" />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(t) => clock(t, startClock)} stroke="var(--muted)" tick={{ fontSize: 11 }} />
          <YAxis domain={[0, cap]} stroke="var(--muted)" tick={{ fontSize: 11 }} width={44} />
          <Tooltip labelFormatter={(t) => clock(Number(t), startClock)} contentStyle={{ background: 'var(--panel)', border: '1px solid var(--border)' }} />
          <ReferenceLine y={lim.H} stroke="var(--warn)" strokeDasharray="4 4" label={{ value: 'H', fill: 'var(--warn)', fontSize: 11, position: 'right' }} />
          <ReferenceLine y={lim.HH} stroke="var(--crit)" strokeDasharray="4 4" label={{ value: 'HH', fill: 'var(--crit)', fontSize: 11, position: 'right' }} />
          <ReferenceLine y={cap} stroke="var(--crit)" label={{ value: 'cap', fill: 'var(--crit)', fontSize: 11, position: 'right' }} />
          <ReferenceLine x={t0} stroke="var(--muted)" />
          {actBy != null && <ReferenceLine x={actBy} stroke="var(--ok)" strokeWidth={2} label={{ value: 'act by', fill: 'var(--ok)', fontSize: 11, position: 'top' }} />}
          <Line dataKey="history" stroke="var(--flow)" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls />
          <Line dataKey="forecast" stroke="var(--warn)" strokeDasharray="6 4" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls />
          <Line dataKey="noaction" stroke="var(--crit)" strokeDasharray="2 4" dot={false} isAnimationActive={false} connectNulls />
          <Line dataKey="option" stroke="var(--ok)" strokeDasharray="6 4" dot={false} strokeWidth={2} isAnimationActive={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>}
    </div>
  )
}
