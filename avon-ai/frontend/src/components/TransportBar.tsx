import { useState } from 'react'
import { FaultPanel } from './FaultPanel'
import { WorkspaceDialog } from './WorkspaceDialog'
import { api } from '../api'
import type { Envelope, Network } from '../types'

interface Props { env: Envelope; network: Network; connected: boolean; run: (fn: () => Promise<unknown>) => Promise<void> }

export function TransportBar({ env, network, connected, run }: Props) {
  const [toolsOpen, setToolsOpen] = useState(false)
  const speeds: number[] = network.config.ui.speeds
  return (
    <header className="transport">
      <div className="plant-identity"><div className="brand">NIGHTWATCH</div><span>Data center cooling operations</span></div>
      <div className="connection"><span className={`dot ${connected ? 'ok' : 'bad'}`} />{connected ? 'Connected' : 'Reconnecting'}</div>
      <div className="clock"><span>Simulation time</span>{env.state.clock} <small>T+{env.state.t_min} min</small></div>
      <div className="spacer" />
      <div className="playback" role="group" aria-label="Simulation playback">
      <button className="primary" onClick={() => run(env.running ? api.pause : api.start)}>{env.running ? '❚❚ Pause' : '▶ Play'}</button>
      <button onClick={() => run(api.step)} disabled={env.running}>Step</button>
      <div className="seg" role="group" aria-label="Playback speed">
        {speeds.map((x) => (
          <button key={x} aria-pressed={env.speed === x} className={env.speed === x ? 'on' : ''} onClick={() => run(() => api.speed(x))}>{x}×</button>
        ))}
      </div>
      </div>
      <button className="tools-trigger" aria-haspopup="dialog" onClick={() => setToolsOpen(true)}>Simulation tools</button>
      <WorkspaceDialog open={toolsOpen} onClose={() => setToolsOpen(false)} title="Simulation tools">
      <div className="simulation-settings">
      <label>Scenario
      <select title={env.scenario.description} aria-label="Scenario" value={env.scenario.id} onChange={(e) => run(() => api.loadScenario(e.target.value))}>
        {network.scenarios.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
      </select></label>
      <button onClick={() => run(api.reset)}>⟲ Reset</button>
      <label className="toggle" title="Layer 2: also start the standby chiller pump when the duty pump delivers low flow (default off, so degradation shows the gap NIGHTWATCH fills)">
        <input type="checkbox" checked={env.auto_changeover_on_low_flow}
          onChange={(e) => run(() => api.patchConfig({ control: { auto_changeover_on_low_flow: e.target.checked } }))} />
        Auto-changeover on low flow
      </label>
      <label className="toggle" title="Disable NIGHTWATCH to show the interlock works on its own">
        <input type="checkbox" checked={env.engine_enabled} onChange={(e) => run(() => api.engine(e.target.checked))} />
        Decision engine
      </label>
      </div>
      <FaultPanel env={env} network={network} run={run} />
      </WorkspaceDialog>
    </header>
  )
}
