import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { clock } from '../format'

export interface StackSeries { key: string; label: string; color: string; dash?: string; faint?: boolean }
export interface StackPanel {
  title: string
  unit: string
  series: StackSeries[]
  thresholds?: { y: number; label: string; color: string }[]
  domain?: [number | 'auto', number | 'auto']
}
export interface StackEvent { t: number; kind: string; label: string }
type Row = { t: number } & Record<string, number | null>

const EVENT_COLOR: Record<string, string> = {
  fault: 'var(--crit)', trip: 'var(--crit)', auto: 'var(--ok)', approval: 'var(--flow)', alarm: 'var(--warn)',
}

/** Stacked panels (one unit each, no dual axes) on a shared time axis with a linked cursor. Reusable by a tank tab. */
export function TimeSeriesStack({ data, panels, events, startClock, height }: {
  data: Row[]; panels: StackPanel[]; events: StackEvent[]; startClock: string; height: number
}) {
  const t0 = data.length ? data[0].t : 0
  const t1 = data.length ? data[data.length - 1].t : 1
  return (
    <div>
      {panels.map((p, i) => (
        <div key={p.title}>
          <div className="stack-title">
            {p.title} <span className="hint">({p.unit})</span>
            {p.series.map((s) => <span key={s.key} className="hint" style={{ color: s.color, marginLeft: 8 }}>{s.dash ? '┅' : '━'} {s.label}</span>)}
          </div>
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={data} syncId="stack" margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
              <CartesianGrid stroke="var(--grid)" />
              <XAxis dataKey="t" type="number" domain={[t0, t1 === t0 ? t0 + 1 : t1]} hide={i < panels.length - 1}
                tickFormatter={(t) => clock(t, startClock)} stroke="var(--muted)" tick={{ fontSize: 11 }} allowDataOverflow />
              <YAxis domain={p.domain ?? ['auto', 'auto']} stroke="var(--muted)" tick={{ fontSize: 11 }} width={40} />
              <Tooltip labelFormatter={(t) => clock(Number(t), startClock)} contentStyle={{ background: 'var(--panel)', border: '1px solid var(--border)' }} />
              {p.thresholds?.map((th) => <ReferenceLine key={th.label} y={th.y} stroke={th.color} strokeDasharray="4 4" label={{ value: th.label, fill: th.color, fontSize: 10, position: 'right' }} />)}
              {events.filter((e) => e.t >= t0 && e.t <= t1).map((e, k) => (
                <ReferenceLine key={`${e.t}-${k}`} x={e.t} stroke={EVENT_COLOR[e.kind] ?? 'var(--muted)'} strokeDasharray="3 3"
                  label={i === 0 ? { value: e.kind, fill: EVENT_COLOR[e.kind] ?? 'var(--muted)', fontSize: 9, position: 'top' } : undefined} />
              ))}
              {p.series.map((s) => (
                <Line key={s.key} dataKey={s.key} stroke={s.color} strokeDasharray={s.dash} strokeOpacity={s.faint ? 0.45 : 1}
                  strokeWidth={s.faint ? 1.5 : 2} dot={false} isAnimationActive={false} connectNulls />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      ))}
    </div>
  )
}
