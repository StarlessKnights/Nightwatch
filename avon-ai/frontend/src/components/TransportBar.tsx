import { api } from '../api'
import { money } from '../format'
import type { Envelope, Network } from '../types'

interface Props { env: Envelope; network: Network; connected: boolean; run: (fn: () => Promise<unknown>) => Promise<void> }

export function TransportBar({ env, network, connected, run }: Props) {
  const speeds: number[] = network.config.ui.speeds
  return (
    <div className="transport">
      <div className="brand">AVON&nbsp;AI</div>
      <button className="primary" onClick={() => run(env.running ? api.pause : api.start)}>{env.running ? '❚❚ Pause' : '▶ Play'}</button>
      <button onClick={() => run(api.step)} disabled={env.running}>Step</button>
      <div className="seg">
        {speeds.map((x) => (
          <button key={x} className={env.speed === x ? 'on' : ''} onClick={() => run(() => api.speed(x))}>{x}×</button>
        ))}
      </div>
      <button onClick={() => run(api.reset)}>⟲ Reset</button>
      <select value={env.scenario.id} onChange={(e) => run(() => api.loadScenario(e.target.value))} title={env.scenario.description}>
        {network.scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select>
      <label className="toggle" title="Layer 2: also start the standby when the duty pump delivers low flow (default off, so degradation shows the gap AVON AI fills)">
        <input type="checkbox" checked={env.auto_changeover_on_low_flow}
          onChange={(e) => run(() => api.patchConfig({ control: { auto_changeover_on_low_flow: e.target.checked } }))} />
        auto-changeover on low flow
      </label>
      <label className="toggle" title="Disable AVON AI to show the interlock works on its own">
        <input type="checkbox" checked={env.engine_enabled} onChange={(e) => run(() => api.engine(e.target.checked))} />
        decision engine
      </label>
      <div className="spacer" />
      <div className="ledger" title={Object.entries(env.ledger.breakdown).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${money(v)}`).join('\n')
        + '\nSaved = projected avoided cost of approved actions vs do-nothing, credited at approval.'}>
        <span className="loss">Loss {money(env.ledger.loss)}</span>
        <span className="save">Saved {money(env.ledger.saved)}</span>
        <span className={env.ledger.net >= 0 ? 'save' : 'loss'}>Net {money(env.ledger.net)}</span>
      </div>
      <div className={`dot ${connected ? 'ok' : 'bad'}`} title={connected ? 'connected' : 'reconnecting…'} />
      <div className="clock">T+{env.state.t_min} min · {env.state.clock}</div>
    </div>
  )
}
