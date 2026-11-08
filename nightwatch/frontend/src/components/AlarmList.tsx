import { api } from '../api'
import type { Envelope } from '../types'

export function AlarmList({ env, run }: { env: Envelope; run: (fn: () => Promise<unknown>) => Promise<void> }) {
  const order = { ACTIVE_UNACK: 0, ACTIVE_ACK: 1, CLEARED: 2 }
  const alarms = [...env.state.alarms].sort((a, b) => order[a.state] - order[b.state] || a.priority - b.priority || b.raised_min - a.raised_min)
  return (
    <div className="panel-fill scroll">
      <div className="panel-head"><h3>Alarms</h3><span className="hint">{alarms.filter((a) => a.state !== 'CLEARED').length} active</span></div>
      {alarms.length === 0 && <div className="hint pad">No alarms</div>}
      {alarms.map((a) => (
        <div key={a.id} className={`alarm p${a.priority} ${a.state === 'CLEARED' ? 'cleared' : a.state === 'ACTIVE_UNACK' ? 'unack' : ''}`}>
          <span className="chip">{a.kind === 'PREDICTIVE' ? 'PREDICTIVE' : `P${a.priority}`}</span>
          <div className="grow"><b>{a.tag}</b> {a.condition.replace(/_/g, ' ')}
            <div className="hint">T+{a.raised_min}{a.cleared_min != null ? ` → cleared T+${a.cleared_min}` : ''}{a.value != null ? ` · ${a.value.toFixed(1)}` : ''} · {a.state.replace('_', ' ')}</div></div>
          {a.state === 'ACTIVE_UNACK' && <button onClick={() => run(() => api.ack(a.id))}>Ack</button>}
        </div>
      ))}
    </div>
  )
}
