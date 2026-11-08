import { useState } from 'react'
import { FaultPanel } from './FaultPanel'
import { WorkspaceDialog } from './WorkspaceDialog'
import { api } from '../api'
import type { Envelope, Network } from '../types'

interface Props { env: Envelope; network: Network; connected: boolean; run: (fn: () => Promise<unknown>) => Promise<void> }


function LunarMoonLogo() {
  return (
    <svg className="lunar-moon-logo" viewBox="0 0 32 32" width="28" height="28" fill="none" aria-hidden="true">
      <defs>
        <radialGradient id="moonAura" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#c084fc" stopOpacity="0.8" />
          <stop offset="60%" stopColor="#38bdf8" stopOpacity="0.3" />
          <stop offset="100%" stopColor="transparent" />
        </radialGradient>
        <linearGradient id="moonDisc" x1="4" y1="4" x2="28" y2="28">
          <stop offset="0%" stopColor="#ffffff" />
          <stop offset="50%" stopColor="#e2e8f0" />
          <stop offset="100%" stopColor="#94a3b8" />
        </linearGradient>
      </defs>
      <circle cx="16" cy="16" r="15" fill="url(#moonAura)" />
      <circle cx="16" cy="16" r="11" fill="url(#moonDisc)" />
      <path d="M16 5C22.075 5 27 9.925 27 16C27 22.075 22.075 27 16 27C19.5 24 21 19 21 16C21 13 19.5 8 16 5Z" fill="#0f172a" opacity="0.82" />
      <circle cx="11" cy="13" r="2.2" fill="#94a3b8" opacity="0.6" />
      <circle cx="14" cy="20" r="1.6" fill="#94a3b8" opacity="0.5" />
      <circle cx="9" cy="18" r="1.1" fill="#94a3b8" opacity="0.5" />
    </svg>
  )
}

function StarGlint({ style, delay = '0s' }: { style?: React.CSSProperties; delay?: string }) {
  return (
    <span className="glowing-star" style={{ ...style, animationDelay: delay }} aria-hidden="true">
      ✦
    </span>
  )
}

export function TransportBar({ env, network, connected, run }: Props) {
  const [toolsOpen, setToolsOpen] = useState(false)
  const speeds: number[] = network.config.ui.speeds
  return (
    <header className="transport">
      <div className="plant-identity">
        <LunarMoonLogo />
        <div className="brand-group">
          <div className="brand">NIGHTWATCH <span className="star-twinkle">✦</span></div>
        </div>
        <StarGlint style={{ marginLeft: 8 }} delay="0.5s" />
      </div>
      <div className="connection"><span className={`dot ${connected ? 'ok' : 'bad'}`} />{connected ? 'Connected' : 'Reconnecting'}</div>
      <div className="clock"><span>Simulation time</span>{env.state.clock} <small>T+{env.state.t_min} min</small></div>
      <div className="spacer">
        <div className="header-star-field">
          <StarGlint delay="0.2s" />
          <StarGlint delay="1.1s" style={{ opacity: 0.6 }} />
          <StarGlint delay="1.8s" style={{ opacity: 0.4 }} />
        </div>
      </div>
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
        <FaultPanel network={network} env={env} run={run} />
      </WorkspaceDialog>
    </header>
  )
}
