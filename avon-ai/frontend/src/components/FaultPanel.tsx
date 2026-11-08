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
  const pumps = env.state.pumps

  return (
    <div className="drawer">
      {/* Interactive Pump Hardware Controls (Real-Time Hardware Testing) */}
      <h3>Pump Controls (Hardware Test)</h3>
      <div className="hint" style={{ marginBottom: 8 }}>Trip, Wear slider (0–1), Shutdown, and Pump Reset.</div>
      {Object.entries(pumps).map(([pid, p]) => {
        const tripFault = env.state.faults.find((f) => f.type === 'PUMP_TRIP' && f.target === pid && f.active)
        const isTripped = p.run_state === 'TRIPPED' || !!tripFault
        const wear = (p.health as number | undefined) ?? (p.eff_health as number | undefined) ?? (p.capacity_factor as number | undefined) ?? 1.0
        const isBadWear = wear < 0.5
        const borderCol = isTripped ? 'var(--crit)' : !p.available ? '#555' : isBadWear ? 'var(--warn)' : 'var(--ok)'

        return (
          <div key={pid} className="card" style={{ borderLeft: `4px solid ${borderCol}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 }}>
              <b>{pid} <span className="hint">({p.role})</span></b>
              <span className={`chip ${isTripped ? 'crit' : !p.available ? '' : p.run_state === 'RUNNING' ? 'ok' : ''}`}>
                {!p.available ? 'UNAVAILABLE' : p.run_state}
              </span>
            </div>

            {/* Hardware Presence & Sensor Badges */}
            <div style={{ display: 'flex', gap: '6px', alignItems: 'center', marginBottom: 6, fontSize: '11px', flexWrap: 'wrap' }}>
              <span style={{ 
                color: p.hardware_online ? '#4ade80' : '#888',
                fontWeight: 600,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px'
              }}>
                <span style={{ 
                  display: 'inline-block',
                  width: 7,
                  height: 7,
                  borderRadius: '50%',
                  background: p.hardware_online ? '#22c55e' : '#555'
                }} />
                {p.hardware_online ? 'HW Connected' : 'HW Offline'}
              </span>

              {p.temperature_c != null && (
                <span style={{ color: 'var(--muted)', background: 'var(--panel2)', padding: '1px 5px', borderRadius: 4 }}>
                  🌡️ {p.temperature_c.toFixed(1)}°C
                </span>
              )}

              {p.knob_factor != null && (
                <span style={{ color: '#38bdf8', background: 'var(--panel2)', padding: '1px 5px', borderRadius: 4 }}>
                  🎛️ Knob {(p.knob_factor * 100).toFixed(0)}%
                </span>
              )}
            </div>

            {/* 1. Trip Button (Error occurring in pump) */}
            <div style={{ marginTop: 6 }}>
              <button
                className="danger"
                style={{ width: '100%', padding: '4px 8px', fontSize: '11px', background: isTripped ? '#8b2020' : undefined }}
                onClick={() => run(async () => {
                  if (tripFault) {
                    await api.clearFault(tripFault.id)
                  } else {
                    await api.injectFault('PUMP_TRIP', pid, {})
                  }
                })}
              >
                {isTripped ? '⚡ Reset Trip Error' : '⚡ Trip Pump (Fault)'}
              </button>
            </div>

            {/* 2. Wear Slider (0 to 1, Bad < 0.5) */}
            <div style={{ marginTop: 8 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--muted)' }}>
                <span>Wear Health:</span>
                <span style={{ color: isBadWear ? '#f87171' : '#4ade80', fontWeight: 'bold' }}>
                  {(wear * 100).toFixed(0)}% {isBadWear ? '⚠ Bad (<0.5)' : 'OK'}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={wear}
                style={{ width: '100%', margin: '4px 0' }}
                onChange={(e) => {
                  const val = Number(e.target.value)
                  run(() => api.patchAsset(pid, { health: val, capacity_factor: val }))
                }}
              />
            </div>

            {/* 3. Availability Button (Operator manual shut down / lockout) */}
            <div style={{ marginTop: 6 }}>
              <button
                style={{
                  width: '100%',
                  padding: '4px 8px',
                  fontSize: '11px',
                  background: !p.available ? '#4a3b1a' : 'var(--panel2)',
                  borderColor: !p.available ? 'var(--warn)' : 'var(--border)'
                }}
                onClick={() => run(() => api.patchAsset(pid, { available: !p.available }))}
              >
                {!p.available ? '🔓 Restore Availability' : '🔒 Shut Down (Operator Lockout)'}
              </button>
            </div>

            {/* 4. Reset Button (Restore this specific pump to pristine 100% normal) */}
            <div style={{ marginTop: 6 }}>
              <button
                style={{
                  width: '100%',
                  padding: '3px 8px',
                  fontSize: '11px',
                  background: 'var(--panel)',
                  border: '1px solid var(--border)',
                  color: 'var(--text)',
                  cursor: 'pointer'
                }}
                title="Clears faults on this pump, resets wear to 100%, and restores availability"
                onClick={() => run(async () => {
                  const targetedFaults = env.state.faults.filter((f) => f.target === pid)
                  for (const f of targetedFaults) {
                    await api.clearFault(f.id)
                  }
                  await api.patchAsset(pid, { health: 1.0, capacity_factor: 1.0, available: true })
                })}
              >
                🔄 Reset {pid} to Normal (100%)
              </button>
            </div>
          </div>
        )
      })}

      <h3>Active faults</h3>
      {env.state.faults.length === 0 && <div className="hint">None</div>}
      {env.state.faults.map((f) => (
        <div key={f.id} className={`fault-row ${f.active ? '' : 'pending'}`}>
          <div><b>{f.type.replace(/_/g, ' ')}</b> · {f.target}<div className="hint">{f.active ? 'active' : `starts T+${f.start_min}`} · {JSON.stringify(f.params)}</div></div>
          <button onClick={() => run(() => api.clearFault(f.id))}>Clear</button>
        </div>
      ))}

      <h3>Inject catalog fault</h3>
      {Object.entries(network.fault_catalog).map(([type, spec]) => (
        <FaultCard key={type} type={type} spec={spec} network={network} run={run} />
      ))}
    </div>
  )
}
