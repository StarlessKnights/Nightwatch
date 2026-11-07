import { useState } from 'react'
import { AlarmList } from './components/AlarmList'
import { EventLog } from './components/EventLog'
import { FaultPanel } from './components/FaultPanel'
import { NetworkDiagram } from './components/NetworkDiagram'
import { Recommendations } from './components/Recommendations'
import { TankTrends } from './components/TankTrends'
import { TransportBar } from './components/TransportBar'
import { useSim } from './useSim'
import './App.css'

export default function App() {
  const { network, env, history, events, rec, connected, error, run } = useSim()
  const [drawer, setDrawer] = useState(true)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  if (!network || !env) return <div className="loading">{error ?? 'Connecting to AVON AI backend…'}</div>
  const disclaimer: string = network.config.ui.disclaimer
  const sel = rec?.options.find((o) => o.action_id === (selectedId ?? rec.best_option_id)) ?? null

  return (
    <div className="app">
      <TransportBar env={env} network={network} connected={connected} run={run} />
      {error && <div className="error" onClick={() => run(async () => undefined)}>{error}</div>}
      <div className="main">
        <button className="drawer-toggle" onClick={() => setDrawer(!drawer)}>{drawer ? '◀ Faults' : '▶ Faults'}</button>
        {drawer && <FaultPanel env={env} network={network} run={run} />}
        <div className="center"><NetworkDiagram env={env} network={network} /></div>
        <div className="right">
          <Recommendations env={env} rec={rec} selectedId={selectedId} onSelect={setSelectedId} run={run} disclaimer={disclaimer} />
          <AlarmList env={env} run={run} />
        </div>
      </div>
      <div className="bottom">
        <TankTrends env={env} network={network} history={history} rec={rec} selected={sel} />
        <EventLog events={events} />
      </div>
      <footer className="footer">⚠ {disclaimer}</footer>
    </div>
  )
}
