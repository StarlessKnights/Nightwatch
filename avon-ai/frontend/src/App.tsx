import { useState } from 'react'
import { AlarmList } from './components/AlarmList'
import { EventLog } from './components/EventLog'
import { FaultPanel } from './components/FaultPanel'
import { CyberCommandCenter } from './components/CyberCommandCenter'
import { WorkspaceDialog } from './components/WorkspaceDialog'
import { money, clock } from './format'
import { NetworkDiagram } from './components/NetworkDiagram'
import { PumpDetailPanel } from './components/PumpDetailPanel'
import { Recommendations } from './components/Recommendations'
import { TankTrends } from './components/TankTrends'
import { TransportBar } from './components/TransportBar'
import { useSim } from './useSim'
import { useAgent } from './useAgent'
import { IntelligencePanel } from './components/IntelligencePanel'
import './App.css'
import './intelligence.css'
import './workspace.css'

export default function App() {
  const { network, env, history, events, rec, connected, error, run } = useSim()
  const [inspectorOpen, setInspectorOpen] = useState(true)
  const [trendsOpen, setTrendsOpen] = useState(true)
  const [alarmsOpen, setAlarmsOpen] = useState(false)
  const [activityOpen, setActivityOpen] = useState(false)
  const [faultsOpen, setFaultsOpen] = useState(false)
  const [cyberOpen, setCyberOpen] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const intelligence = useAgent(env?.state.run_id)
  const [showIntelligence, setShowIntelligence] = useState(true)
  const [focus, setFocus] = useState<{ run: string; assets: string[] } | null>(null)

  if (!network || !env) return <div className="loading">{error ?? 'Connecting to NIGHTWATCH backend…'}</div>
  const disclaimer: string = network.config.ui.disclaimer
  const incidentAssets = focus?.run === env.state.run_id ? focus.assets
    : intelligence.data?.incidents?.filter((i) => i?.status === 'active').flatMap((i) => i?.affected_assets ?? []) ?? []
  const sel = rec?.options.find((o) => o.action_id === (selectedId ?? rec.best_option_id)) ?? null

  const activeAlarms = env.state.alarms.filter(a => a.state !== 'CLEARED')
  const unacked = activeAlarms.filter(a => a.state === 'ACTIVE_UNACK').length
  const topAlarm = [...activeAlarms].sort((a, b) => a.priority - b.priority
    || Number(b.state === 'ACTIVE_UNACK') - Number(a.state === 'ACTIVE_UNACK')
    || b.raised_min - a.raised_min)[0]

  const shutInTanks = Object.entries(env.state.tanks).filter(([, tank]) => tank.interlock.tripped).map(([id]) => id)
  const nextHighHigh = Object.values(env.forecast.tanks)
    .filter(forecast => forecast.time_to_HH != null)
    .sort((a, b) => a.time_to_HH! - b.time_to_HH!)[0]
  const forecastAge = Math.max(0, env.state.t_min - env.forecast.as_of_min)
  const minutesToShutdown = nextHighHigh ? Math.max(0, nextHighHigh.time_to_HH! - forecastAge) : null
  const isAirgapActive = env.incident?.airgap_engaged || env.state?.airgap_engaged

  return (
    <div className="app plant-workspace">
      <TransportBar env={env} network={network} connected={connected} run={run} />

      <div className="attention-region">
        {!connected && <div className="connection-warning" role="status">Connection lost. Showing last received readings at T+{env.state.t_min} min. Reconnecting…</div>}
        {isAirgapActive && (
          <div style={{
            background: 'linear-gradient(90deg, rgba(80, 15, 35, 0.95), rgba(40, 10, 30, 0.95))',
            border: '1px solid #f43f5e',
            color: '#fecdd3',
            padding: '8px 18px',
            borderRadius: '10px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            fontSize: '12px',
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
            boxShadow: '0 0 16px rgba(244, 63, 94, 0.4)'
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span style={{ color: '#f43f5e', fontSize: '14px' }}>🔒</span>
              <span>WINSTEAD ALERT: PHYSICAL AIR-GAP KILLSWITCH ENGAGED — EXTERNAL WAN ISOLATED</span>
            </span>
            <button
              onClick={() => setCyberOpen(true)}
              style={{
                background: 'linear-gradient(135deg, #e11d48, #be123c)',
                color: '#fff',
                border: 'none',
                padding: '4px 14px',
                borderRadius: '9999px',
                cursor: 'pointer',
                fontSize: '11px',
                fontWeight: 700,
                letterSpacing: '0.04em',
                boxShadow: '0 0 10px rgba(225, 29, 72, 0.5)'
              }}
            >
              OPEN INCIDENT COMMAND
            </button>
          </div>
        )}
        {error && <div className="workspace-error" role="alert">{error}<button onClick={() => run(async () => undefined)}>Dismiss</button></div>}
        <button className={`attention-strip ${topAlarm ? `priority-${topAlarm.priority}` : ''}`} onClick={() => setAlarmsOpen(true)} aria-haspopup="dialog">
          <span className="attention-symbol" aria-hidden="true">{topAlarm ? '!' : '✓'}</span>
          <span className="attention-message">{topAlarm ? <><strong>{topAlarm.tag}</strong> {topAlarm.text || topAlarm.condition.replaceAll('_', ' ')}<small>Priority {topAlarm.priority} · {topAlarm.state === 'ACTIVE_UNACK' ? 'Needs acknowledgment' : 'Acknowledged'}</small></> : <><strong>No active alarms</strong><small>{connected ? 'Monitoring plant conditions' : 'Based on last received readings'}</small></>}</span>
          <span className="attention-counts">{activeAlarms.length} active <span>{unacked} unacknowledged</span></span>
          <span className="attention-action">View alarms</span>
        </button>
      </div>

      <main className={`plant-main ${inspectorOpen ? '' : 'inspector-collapsed'}`}>
        <section className="graph-workspace" aria-label="Cooling plant network">
          <div className="workspace-heading">
            <div className="workspace-title">
              <h1>Cooling plant network</h1>
              <details className="network-context">
                <summary>About this network</summary>
                <p>IT heat load, chilled-water loops and heat rejection</p>
                <ol className="process-stages" aria-label="Cooling process">
                  <li>IT heat load</li>
                  <li>Hall thermal mass</li>
                  <li>Chillers &amp; loops</li>
                  <li>Heat rejection</li>
                </ol>
                <p>Latest forecast at T+{env.forecast.as_of_min} min.</p>
              </details>
            </div>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <button
                aria-haspopup="dialog"
                style={{
                  background: isAirgapActive
                    ? 'linear-gradient(135deg, #be123c 0%, #e11d48 100%)'
                    : 'linear-gradient(135deg, #7c3aed 0%, #9333ea 50%, #c026d3 100%)',
                  color: '#fff',
                  border: `1px solid ${isAirgapActive ? '#fda4af' : 'rgba(216, 180, 254, 0.5)'}`,
                  fontWeight: 700,
                  fontSize: '12px',
                  letterSpacing: '0.03em',
                  borderRadius: '9999px',
                  padding: '5px 16px',
                  boxShadow: isAirgapActive ? '0 0 16px rgba(244, 63, 94, 0.6)' : '0 0 14px rgba(168, 85, 247, 0.45)'
                }}
                onClick={() => setCyberOpen(true)}
              >
                🛡️ WINSTEAD CYBER COMMAND {isAirgapActive ? '🔒' : ''}
              </button>
              <button
                aria-haspopup="dialog"
                style={{
                  background: 'rgba(36, 25, 69, 0.85)',
                  border: '1px solid rgba(34, 211, 238, 0.4)',
                  color: '#e0f2fe',
                  fontSize: '12px',
                  fontWeight: 600,
                  borderRadius: '9999px',
                  padding: '5px 14px'
                }}
                onClick={() => setFaultsOpen(true)}
              >
                🎛️ HARDWARE &amp; FAULTS
              </button>
              <button
                aria-expanded={inspectorOpen}
                aria-controls="plant-inspector"
                style={{
                  background: 'rgba(26, 18, 51, 0.7)',
                  border: '1px solid var(--border)',
                  color: 'var(--muted)',
                  fontSize: '12px',
                  borderRadius: '9999px',
                  padding: '5px 14px'
                }}
                onClick={() => setInspectorOpen(!inspectorOpen)}
              >
                {inspectorOpen ? 'HIDE INSPECTOR' : 'OPEN INSPECTOR'}
              </button>
            </div>
          </div>

          <div className={`plant-outlook ${shutInTanks.length ? 'is-shut-in' : nextHighHigh ? 'is-at-risk' : 'is-normal'}`}>
            <div>
              <strong>
                {shutInTanks.length
                  ? `IT load shed · ${shutInTanks.join(', ')}`
                  : nextHighHigh
                  ? `${nextHighHigh.tank} · load-shed forecast in ${Math.ceil(minutesToShutdown!)} min`
                  : 'No high-high crossing forecast'}
              </strong>
              {(shutInTanks.length > 0 || nextHighHigh) && (
                <span>
                  {shutInTanks.length
                    ? 'High-high protection has shed IT load.'
                    : nextHighHigh
                    ? `High-high at ${clock(env.forecast.as_of_min + nextHighHigh.time_to_HH!, network.config.ui.start_clock)} sheds IT load to protect against a thermal event.`
                    : ''} Forecast at T+{env.forecast.as_of_min} min.
                </span>
              )}
            </div>
            {(nextHighHigh || shutInTanks.length > 0) && (
              <button onClick={() => { setInspectorOpen(true); setDetailId(null); setShowIntelligence(false) }}>
                Compare responses
              </button>
            )}
          </div>

          <div className="graph-canvas">
            <NetworkDiagram
              key={env.state.run_id}
              env={env}
              network={network}
              onPumpDetail={id => { setDetailId(id); setInspectorOpen(true) }}
              incidentAssets={incidentAssets}
            />
          </div>
          <div className="graph-caption">
            <span><i />Heat removal in kW</span>
            <span>Double-click a chiller pump for details</span>
          </div>
        </section>

        <aside id="plant-inspector" className="right with-intelligence" hidden={!inspectorOpen} aria-label="Plant inspector">
          <div className="right-top">
            {detailId && <PumpDetailPanel id={detailId} env={env} network={network} onClose={() => setDetailId(null)} />}
            <div className="inspector-view" hidden={!!detailId}>
              <div className="panel-switch">
                <button aria-pressed={showIntelligence} className={showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(true)}>NIGHTWATCH Intelligence</button>
                <button aria-pressed={!showIntelligence} className={!showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(false)}>Decision engine</button>
              </div>
              <div className="inspector-view" hidden={!showIntelligence}>
                <IntelligencePanel
                  key={env.state.run_id}
                  data={intelligence.data}
                  error={intelligence.error}
                  run={intelligence.run}
                  onFocus={(ids) => setFocus({ run: env.state.run_id, assets: ids })}
                  assets={network.topology.nodes.map((n) => n.id)}
                />
              </div>
              <div className="inspector-view" hidden={showIntelligence}>
                <Recommendations env={env} rec={rec} selectedId={selectedId} onSelect={setSelectedId} run={run} disclaimer={disclaimer} />
              </div>
            </div>
          </div>
        </aside>
      </main>

      <section className={`trends-region ${trendsOpen ? '' : 'trends-collapsed'}`} aria-label="Trends and activity">
        <div className="trends-toolbar">
          <span>Measured history and forecast</span>
          <div className="trends-actions">
            <button aria-expanded={trendsOpen} aria-controls="tank-trends" onClick={() => setTrendsOpen(!trendsOpen)}>
              {trendsOpen ? 'Hide trends' : 'Show trends'}
            </button>
            <button aria-haspopup="dialog" onClick={() => setActivityOpen(true)}>Activity · {events.length}</button>
          </div>
        </div>
        <div id="tank-trends" className="trends-content" hidden={!trendsOpen}>
          <TankTrends visible={trendsOpen} env={env} network={network} history={history} rec={rec} selected={sel} />
        </div>
      </section>

      <WorkspaceDialog open={alarmsOpen} onClose={() => setAlarmsOpen(false)} title="Plant alarms">
        <AlarmList env={env} run={run} />
      </WorkspaceDialog>

      <WorkspaceDialog open={activityOpen} onClose={() => setActivityOpen(false)} title="Plant activity">
        <div className="activity-ledger">
          <div><span>Simulated loss</span><strong>{money(env.ledger.loss)}</strong></div>
          <div><span>Projected savings</span><strong>{money(env.ledger.saved)}</strong></div>
          <div><span>Net</span><strong>{money(env.ledger.net)}</strong></div>
        </div>
        <p className="hint">Savings are projected avoided costs of approved actions, credited at approval.</p>
        <details className="loss-breakdown">
          <summary>Loss breakdown</summary>
          <dl>
            {Object.entries(env.ledger.breakdown).map(([label, value]) => (
              <div key={label}>
                <dt>{label.replaceAll('_', ' ')}</dt>
                <dd>{money(value)}</dd>
              </div>
            ))}
          </dl>
        </details>
        <EventLog events={events} />
      </WorkspaceDialog>

      <WorkspaceDialog open={faultsOpen} onClose={() => setFaultsOpen(false)} title="Hardware &amp; Fault Controls">
        <FaultPanel env={env} network={network} run={run} />
      </WorkspaceDialog>

      <WorkspaceDialog open={cyberOpen} onClose={() => setCyberOpen(false)} title="Winstead Cyber Incident Command">
        <CyberCommandCenter env={env} run={run} onClose={() => setCyberOpen(false)} />
      </WorkspaceDialog>

      <footer className="footer">
        <span className="simulation-disclaimer">⚠ {disclaimer}</span>
        <span className="copyright-notice">© 2026 Avon Corps. All rights reserved.</span>
        <div className="creator-credit" aria-label="Created by Pericynthion. Powered by NVIDIA Nemotron.">
          <span className="creator-signature">
            <span className="credit-label">Created by</span>
            <span className="pericynthion-wordmark">
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M17.5 3.5a9.5 9.5 0 1 0 3 13.5A8 8 0 0 1 17.5 3.5Z" fill="currentColor" />
                <circle cx="19.5" cy="5" r="1.5" fill="currentColor" />
              </svg>
              Pericynthion
            </span>
          </span>
          <span className="provider-signature">
            <span className="credit-label">Powered by</span>
            <span className="nemotron-wordmark"><span className="nvidia-wordmark">NVIDIA</span> Nemotron</span>
          </span>
        </div>
      </footer>
    </div>
  )
}
