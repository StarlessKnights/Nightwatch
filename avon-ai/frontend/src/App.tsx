import { useState } from 'react'
import { AlarmList } from './components/AlarmList'
import { EventLog } from './components/EventLog'
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
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailId, setDetailId] = useState<string | null>(null)
  const intelligence = useAgent(env?.state.run_id)
  const [showIntelligence, setShowIntelligence] = useState(true)
  const [focus, setFocus] = useState<{ run: string; assets: string[] } | null>(null)

  if (!network || !env) return <div className="loading">{error ?? 'Connecting to AVON AI backend…'}</div>
  const disclaimer: string = network.config.ui.disclaimer
  const incidentAssets = focus?.run === env.state.run_id ? focus.assets
    : intelligence.data?.incidents.filter((i) => i.status === 'active').flatMap((i) => i.affected_assets) ?? []
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

  return (
    <div className="app plant-workspace">
      <TransportBar env={env} network={network} connected={connected} run={run} />
      <div className="attention-region">
        {!connected && <div className="connection-warning" role="status">Connection lost. Showing last received readings at T+{env.state.t_min} min. Reconnecting…</div>}
        {error && <div className="workspace-error" role="alert">{error}<button onClick={() => run(async () => undefined)}>Dismiss</button></div>}
        <button className={`attention-strip ${topAlarm ? `priority-${topAlarm.priority}` : ''}`} onClick={() => setAlarmsOpen(true)} aria-haspopup="dialog">
          <span className="attention-symbol" aria-hidden="true">{topAlarm ? '!' : '✓'}</span>
          <span className="attention-message">{topAlarm ? <><strong>{topAlarm.tag}</strong> {topAlarm.text || topAlarm.condition.replaceAll('_', ' ')}<small>Priority {topAlarm.priority} · {topAlarm.state === 'ACTIVE_UNACK' ? 'Needs acknowledgment' : 'Acknowledged'}</small></> : <><strong>No active alarms</strong><small>{connected ? 'Monitoring plant conditions' : 'Based on last received readings'}</small></>}</span>
          <span className="attention-counts">{activeAlarms.length} active <span>{unacked} unacknowledged</span></span>
          <span className="attention-action">View alarms</span>
        </button>
      </div>
      <main className={`plant-main ${inspectorOpen ? '' : 'inspector-collapsed'}`}>
        <section className="graph-workspace" aria-label="Produced-water network">
          <div className="workspace-heading"><div><h1>Produced-water network</h1><span className="hint">Oilfield saltwater collection and treatment</span></div><button aria-expanded={inspectorOpen} aria-controls="plant-inspector" onClick={() => setInspectorOpen(!inspectorOpen)}>{inspectorOpen ? 'Hide inspector' : 'Open inspector'}</button></div>
          <ol className="process-stages" aria-label="Produced-water process"><li>Oilfield collection</li><li>Saltwater storage</li><li>Pumps &amp; pipelines</li><li>Treatment</li></ol>
          <div className={`plant-outlook ${shutInTanks.length ? 'is-shut-in' : nextHighHigh ? 'is-at-risk' : 'is-normal'}`}>
            <div><strong>{shutInTanks.length ? `Inflow shut in · ${shutInTanks.join(', ')}` : nextHighHigh ? `${nextHighHigh.tank} · inflow shutdown forecast in ${Math.ceil(minutesToShutdown!)} min` : 'No high-high crossing forecast'}</strong>
            <span>{shutInTanks.length ? 'High-high protection has stopped oilfield inflow.' : nextHighHigh ? `High-high at ${clock(env.forecast.as_of_min + nextHighHigh.time_to_HH!, network.config.ui.start_clock)} shuts in inflow to protect against a spill.` : ''} Forecast at T+{env.forecast.as_of_min} min.</span></div>
            {(nextHighHigh || shutInTanks.length > 0) && <button onClick={() => { setInspectorOpen(true); setDetailId(null); setShowIntelligence(false) }}>Compare responses</button>}
          </div>
          <div className="graph-canvas"><NetworkDiagram key={env.state.run_id} env={env} network={network} onPumpDetail={id => { setDetailId(id); setInspectorOpen(true) }} incidentAssets={incidentAssets} /></div>
          <div className="graph-caption"><span><i />Saltwater flow in bbl/hr</span><span>Double-click a pump for details</span></div>
        </section>
        <aside id="plant-inspector" className="right with-intelligence" hidden={!inspectorOpen} aria-label="Plant inspector">
          <div className="right-top">
            {detailId && <PumpDetailPanel id={detailId} env={env} network={network} onClose={() => setDetailId(null)} />}
            <div className="inspector-view" hidden={!!detailId}>
              <div className="panel-switch">
                <button aria-pressed={showIntelligence} className={showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(true)}>AVON Intelligence</button>
                <button aria-pressed={!showIntelligence} className={!showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(false)}>Decision engine</button>
              </div>
              <div className="inspector-view" hidden={!showIntelligence}>
                <IntelligencePanel key={env.state.run_id} data={intelligence.data} error={intelligence.error} run={intelligence.run} onFocus={(ids) => setFocus({ run: env.state.run_id, assets: ids })} assets={network.topology.nodes.map((n) => n.id)} />
              </div>
              <div className="inspector-view" hidden={showIntelligence}>
                <Recommendations env={env} rec={rec} selectedId={selectedId} onSelect={setSelectedId} run={run} disclaimer={disclaimer} />
              </div>
            </div>
          </div>
        </aside>
      </main>
      <section className={`trends-region ${trendsOpen ? '' : 'trends-collapsed'}`} aria-label="Trends and activity">
        <div className="trends-toolbar"><span>Measured history and forecast</span><div className="trends-actions"><button aria-expanded={trendsOpen} aria-controls="tank-trends" onClick={() => setTrendsOpen(!trendsOpen)}>{trendsOpen ? 'Hide trends' : 'Show trends'}</button><button aria-haspopup="dialog" onClick={() => setActivityOpen(true)}>Activity · {events.length}</button></div></div>
        <div id="tank-trends" className="trends-content" hidden={!trendsOpen}>
          <TankTrends visible={trendsOpen} env={env} network={network} history={history} rec={rec} selected={sel} />
        </div>
      </section>
      <WorkspaceDialog open={alarmsOpen} onClose={() => setAlarmsOpen(false)} title="Plant alarms"><AlarmList env={env} run={run} /></WorkspaceDialog>
      <WorkspaceDialog open={activityOpen} onClose={() => setActivityOpen(false)} title="Plant activity">
        <div className="activity-ledger"><div><span>Simulated loss</span><strong>{money(env.ledger.loss)}</strong></div><div><span>Projected savings</span><strong>{money(env.ledger.saved)}</strong></div><div><span>Net</span><strong>{money(env.ledger.net)}</strong></div></div>
        <p className="hint">Savings are projected avoided costs of approved actions, credited at approval.</p>
        <details className="loss-breakdown"><summary>Loss breakdown</summary><dl>{Object.entries(env.ledger.breakdown).map(([label, value]) => <div key={label}><dt>{label.replaceAll('_', ' ')}</dt><dd>{money(value)}</dd></div>)}</dl></details>
        <EventLog events={events} />
      </WorkspaceDialog>
      <footer className="footer">⚠ {disclaimer}</footer>
    </div>
  )
}
