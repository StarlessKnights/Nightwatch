import { useState } from 'react'
import { FaultPanel } from './FaultPanel'
import { WorkspaceDialog } from './WorkspaceDialog'
import { api } from '../api'
import type { Envelope, Network } from '../types'

interface Props {
  env: Envelope
  network: Network
  connected: boolean
  run: (fn: () => Promise<unknown>) => Promise<void>
}

function LunarMoonSprite() {
  return (
    <svg className="lunar-moon-icon" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      {/* Outer Moon Glow Aura */}
      <circle cx="16" cy="16" r="14" fill="url(#moonAura)" opacity="0.45" />
      {/* Moon Base */}
      <circle cx="16" cy="16" r="11" fill="url(#moonGrad)" />
      {/* Pixelated/Vector Craters */}
      <circle cx="12" cy="12" r="2.5" fill="#c4b5fd" opacity="0.6" />
      <circle cx="19" cy="15" r="3.2" fill="#a78bfa" opacity="0.5" />
      <circle cx="13" cy="20" r="1.8" fill="#8b5cf6" opacity="0.5" />
      <circle cx="17" cy="10" r="1.2" fill="#c4b5fd" opacity="0.7" />
      {/* Starlight Glint */}
      <path d="M7 6L7.8 7.8L9.6 8.6L7.8 9.4L7 11.2L6.2 9.4L4.4 8.6L6.2 7.8L7 6Z" fill="#fbbf24" opacity="0.9" />
      <defs>
        <radialGradient id="moonAura" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#d946ef" stopOpacity="0.8" />
          <stop offset="60%" stopColor="#8b5cf6" stopOpacity="0.4" />
          <stop offset="100%" stopColor="#07040d" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="moonGrad" x1="6" y1="6" x2="26" y2="26">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="45%" stopColor="#f3e8ff" />
          <stop offset="100%" stopColor="#c084fc" />
        </linearGradient>
      </defs>
    </svg>
  )
}

export function TransportBar({ env, network, connected, run }: Props) {
  const [toolsOpen, setToolsOpen] = useState(false)
  const speeds: number[] = network.config.ui.speeds

  return (
    <header className="transport lunar-transport">
      <div className="plant-identity">
        <LunarMoonSprite />
        <div className="brand-group">
          <div className="brand lunar-brand">
            NIGHTWATCH <span className="star-twinkle">✦</span>
          </div>
          <span className="brand-subtitle">Lunar Mission · Datacenter Cooling Ops</span>
        </div>
      </div>

      <div className="connection">
        <span className={`dot ${connected ? 'ok' : 'bad'}`} />
        <span className="connection-text">{connected ? 'TELEMETRY LIVE' : 'SIGNAL SEARCHING…'}</span>
      </div>

      <div className="clock lunar-clock">
        <span className="clock-label">MISSION CLOCK</span>
        <strong className="clock-time">{env.state.clock}</strong>
        <span className="clock-elapsed">T+{env.state.t_min}m</span>
      </div>

      <div className="spacer" />

      <div className="playback" role="group" aria-label="Simulation playback">
        <button
          className="primary lunar-cta-btn"
          onClick={() => run(env.running ? api.pause : api.start)}
        >
          {env.running ? '❚❚ PAUSE' : '▶ RESUME'}
        </button>
        <button className="lunar-btn" onClick={() => run(api.step)} disabled={env.running}>
          STEP
        </button>
        <div className="seg lunar-seg" role="group" aria-label="Playback speed">
          {speeds.map((x) => (
            <button
              key={x}
              aria-pressed={env.speed === x}
              className={env.speed === x ? 'on' : ''}
              onClick={() => run(() => api.speed(x))}
            >
              {x}×
            </button>
          ))}
        </div>
      </div>

      <button
        className="tools-trigger lunar-btn-outline"
        aria-haspopup="dialog"
        onClick={() => setToolsOpen(true)}
      >
        ⚙️ SIMULATION TOOLS
      </button>

      <WorkspaceDialog open={toolsOpen} onClose={() => setToolsOpen(false)} title="Simulation Tools &amp; Scenario Config">
        <div className="simulation-settings">
          <label>
            Active Mission Scenario
            <select
              title={env.scenario.description}
              aria-label="Scenario"
              value={env.scenario.id}
              onChange={(e) => run(() => api.loadScenario(e.target.value))}
            >
              {network.scenarios.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          <button onClick={() => run(api.reset)}>⟲ Reset State</button>
          <label
            className="toggle"
            title="Layer 2: start standby chiller pump when duty pump delivers low flow"
          >
            <input
              type="checkbox"
              checked={env.auto_changeover_on_low_flow}
              onChange={(e) =>
                run(() =>
                  api.patchConfig({
                    control: { auto_changeover_on_low_flow: e.target.checked }
                  })
                )
              }
            />
            Auto-changeover on low flow
          </label>
          <label className="toggle" title="Disable NIGHTWATCH to evaluate standalone loop interlocks">
            <input
              type="checkbox"
              checked={env.engine_enabled}
              onChange={(e) => run(() => api.engine(e.target.checked))}
            />
            NIGHTWATCH Decision Engine
          </label>
        </div>
        <FaultPanel env={env} network={network} run={run} />
      </WorkspaceDialog>
    </header>
  )
}
