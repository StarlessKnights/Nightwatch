import { useState, type CSSProperties } from 'react'
import { AlarmList } from './components/AlarmList'
import { EventLog } from './components/EventLog'
import { FaultPanel } from './components/FaultPanel'
import { NetworkDiagram } from './components/NetworkDiagram'
import { Recommendations } from './components/Recommendations'
import { TankTrends } from './components/TankTrends'
import { TransportBar } from './components/TransportBar'
import { useSim } from './useSim'
import { useAgent } from './useAgent'
import { IntelligencePanel } from './components/IntelligencePanel'
import './App.css'
import './operator.css'

export default function App() {
  const { network, env, history, events, rec, connected, error, run } = useSim()
  const intelligence = useAgent(env?.state.run_id)
  const [showIntelligence, setShowIntelligence] = useState(true)
  const [focus, setFocus] = useState<{ run: string; assets: string[] } | null>(null)
  const [drawer, setDrawer] = useState(false)
  const [deskWidth, setDeskWidth] = useState<number | null>(null)
  const resize = (width: number) => setDeskWidth(Math.round(Math.max(290, Math.min(window.innerWidth - 290, width))))
  const [dock, setDock] = useState('Trends'), [mobileDesk, setMobileDesk] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (!network || !env) return <div className="loading">{error ?? 'Connecting to AVON AI backend…'}</div>
  const disclaimer: string = network.config.ui.disclaimer
  const sel = rec?.options.find((o) => o.action_id === (selectedId ?? rec.best_option_id)) ?? null

  return (
    <div className="app">
      <TransportBar env={env} network={network} connected={connected} run={run} />
      {error && <div className="error" onClick={() => run(async () => undefined)}>{error}</div>}
      <AlarmList env={env} run={run} />
      <nav className="mobile-switch desk-tabs"><button aria-pressed={mobileDesk} onClick={() => setMobileDesk(true)}>Operator desk</button><button aria-pressed={!mobileDesk} onClick={() => setMobileDesk(false)}>Network</button></nav>
      <div className={"main console " + (mobileDesk ? "show-desk" : "show-network")} style={{ '--desk-width': deskWidth ? deskWidth + 'px' : undefined } as CSSProperties}>
        <section className="plant-workspace"><div className="plant-map">
        <button className="drawer-toggle" onClick={() => setDrawer(!drawer)}>{drawer ? '◀ Faults' : '▶ Faults'}</button>
        {drawer && <FaultPanel env={env} network={network} run={run} />}
        <div className="center"><NetworkDiagram key={env.state.run_id} env={env} network={network} incidentAssets={focus?.run === env.state.run_id ? focus.assets : intelligence.data?.incidents.filter((i) => i.status === 'active').flatMap((i) => i.affected_assets) ?? []} /></div>
        </div><nav className="desk-tabs dock-switch" aria-label="Network views">{['Trends','Events'].map(name => <button aria-pressed={dock === name} key={name} onClick={() => setDock(name)}>{name === 'Trends' ? 'Tank trends' : 'Event log'}</button>)}</nav>
        <div className="network-dock">{dock === 'Trends' ? <TankTrends env={env} network={network} history={history} rec={rec} selected={sel} /> : <EventLog events={events} />}</div></section>
        <div className="desk-divider" role="separator" aria-label="Resize operator desk" aria-orientation="vertical" tabIndex={0}
          aria-valuemin={290} aria-valuemax={window.innerWidth - 290} aria-valuenow={deskWidth ?? Math.round(Math.min(540, Math.max(370, window.innerWidth * .35)))}
          onPointerDown={e => { e.preventDefault(); e.currentTarget.setPointerCapture(e.pointerId) }}
          onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) resize(e.currentTarget.parentElement!.getBoundingClientRect().right - e.clientX) }}
          onDoubleClick={() => setDeskWidth(null)}
          onKeyDown={e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); resize(e.currentTarget.nextElementSibling!.getBoundingClientRect().width + (e.key === 'ArrowLeft' ? 24 : -24)) } }} />
        <div className="right with-intelligence">
          <div className="panel-switch"><button aria-pressed={showIntelligence} className={showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(true)}>AVON Intelligence</button><button aria-pressed={!showIntelligence} className={!showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(false)}>Decision engine</button></div>
          {showIntelligence ? <IntelligencePanel key={env.state.run_id} data={intelligence.data} error={intelligence.error} run={intelligence.run} onFocus={ids => { setFocus({run: env.state.run_id, assets: ids}); setMobileDesk(false) }} assets={network.topology.nodes.map((n) => n.id)} /> : <Recommendations env={env} rec={rec} selectedId={selectedId} onSelect={setSelectedId} run={run} disclaimer={disclaimer} />}

        </div>
      </div>
      <footer className="footer">⚠ {disclaimer}</footer>
    </div>
  )
}
