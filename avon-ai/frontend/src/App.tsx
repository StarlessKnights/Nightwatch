import { useState } from 'react'
import { AlarmList } from './components/AlarmList'
import { EventLog } from './components/EventLog'
import { FaultPanel } from './components/FaultPanel'
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

export default function App() {
  const { network, env, history, events, rec, connected, error, run } = useSim()
  const [drawer, setDrawer] = useState(true)
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

  return (
    <div className="app">
      <TransportBar env={env} network={network} connected={connected} run={run} />
      {error && <div className="error" onClick={() => run(async () => undefined)}>{error}</div>}
      <div className="main">
        <button className="drawer-toggle" onClick={() => setDrawer(!drawer)}>{drawer ? '◀ Faults' : '▶ Faults'}</button>
        {drawer && <FaultPanel env={env} network={network} run={run} />}
        <div className="center"><NetworkDiagram key={env.state.run_id} env={env} network={network} onPumpDetail={setDetailId} incidentAssets={incidentAssets} /></div>
      </div>
        <div className="right with-intelligence">
          <div className="right-top">
            {detailId
              ? <PumpDetailPanel id={detailId} env={env} network={network} onClose={() => setDetailId(null)} />
              : <>
                <div className="panel-switch">
                  <button aria-pressed={showIntelligence} className={showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(true)}>AVON Intelligence</button>
                  <button aria-pressed={!showIntelligence} className={!showIntelligence ? 'on' : ''} onClick={() => setShowIntelligence(false)}>Decision engine</button>
                </div>
                {showIntelligence
                  ? <IntelligencePanel key={env.state.run_id} data={intelligence.data} error={intelligence.error} run={intelligence.run} onFocus={(ids) => setFocus({ run: env.state.run_id, assets: ids })} assets={network.topology.nodes.map((n) => n.id)} />
                  : <Recommendations env={env} rec={rec} selectedId={selectedId} onSelect={setSelectedId} run={run} disclaimer={disclaimer} />}
              </>}
          </div>
          <AlarmList env={env} run={run} />
        </div>
      <div className="bottom">
        <TankTrends env={env} network={network} history={history} rec={rec} selected={sel} />
        <EventLog events={events} />
      </div>
      <footer className="footer">⚠ {disclaimer}</footer>
    </div>
  )
}
