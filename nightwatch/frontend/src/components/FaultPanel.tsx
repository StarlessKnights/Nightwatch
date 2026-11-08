import { useState } from 'react'
import { api } from '../api'
import type { Envelope, Json, Network } from '../types'

interface Props { env: Envelope; network: Network; run: (fn: () => Promise<unknown>) => Promise<void> }

function FaultCard({ type, spec, network, run }: { type: string; spec: Network['fault_catalog'][string]; network: Network; run: Props['run'] }) {
  const targets = network.topology.nodes.filter((n) => n.type === spec.target_kind)
  const [target, setTarget] = useState(targets[0]?.id ?? '')
  const [params, setParams] = useState<Json>(() => Object.fromEntries(Object.entries(spec.params).map(([k, v]) => [k, v.default])))
  return (
    <div className="card">
      <div className="card-title">{type.replace(/_/g, ' ')}</div>
      <div className="hint">{spec.handled_by}</div>
      <select value={target} onChange={(e) => setTarget(e.target.value)}>
        {targets.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
      </select>
      {Object.entries(spec.params).map(([k, v]) =>
        v.options ? (
          <label key={k} className="row">{k}
            <select value={params[k]} onChange={(e) => setParams({ ...params, [k]: e.target.value })}>
              {v.options.map((o: string) => <option key={o}>{o}</option>)}
            </select>
          </label>
        ) : (
          <label key={k} className="row">{k}
            <input type="range" min={v.min} max={v.max} step={v.step} value={params[k] ?? v.min}
              onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })} />
            <span className="val">{params[k] ?? 'auto'}</span>
          </label>
        ))}
      <button className="danger" onClick={() => run(() => api.injectFault(type, target, params))}>Inject</button>
    </div>
  )
}

export function FaultPanel({ env, network, run }: Props) {
  return (
    <div className="drawer">
      <h3>Active faults</h3>
      {env.state.faults.length === 0 && <div className="hint">None</div>}
      {env.state.faults.map((f) => (
        <div key={f.id} className={`fault-row ${f.active ? '' : 'pending'}`}>
          <div><b>{f.type.replace(/_/g, ' ')}</b> · {f.target}<div className="hint">{f.active ? 'active' : `starts T+${f.start_min}`} · {JSON.stringify(f.params)}</div></div>
          <button onClick={() => run(() => api.clearFault(f.id))}>Clear</button>
        </div>
      ))}
      <h3>Inject fault</h3>
      {Object.entries(network.fault_catalog).map(([type, spec]) => (
        <FaultCard key={type} type={type} spec={spec} network={network} run={run} />
      ))}
    </div>
  )
}
