import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeChange, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api } from '../api'
import type { Envelope, Network } from '../types'
import type { AgentState, TeamReport } from '../agentTypes'
import { eventText } from '../format'
import './investigation.css'

const COL_W = 230
const ROW_H = 120
const FLOW_EPS = 0.5 // kW below which an edge is drawn as "no flow"

type D = { node: any; env: Envelope; network: Network; dim: boolean; onDetails?: (id: string) => void; report?: TeamReport; selected?: boolean; select?: () => void }

const agentNames: Record<string, string> = { 'Thermal Capacity Agent': 'Thermal capacity', 'Cooling Reliability Agent': 'Cooling reliability', 'Workload Placement Agent': 'Workload placement', 'Incident Commander': 'Incident commander' }
function InvestigationNode({ data }: NodeProps<Node<D>>) {
  const report = data.report!
  return <button className={`investigation-node nodrag ${report.status === 'Reviewing' ? 'is-reviewing' : ''}`} aria-pressed={data.selected} onClick={data.select}>
    <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
    <span className="agent-orbit" aria-hidden="true"><i /></span>
    <span><strong>{agentNames[report.role] ?? report.role}</strong><small>{report.source === 'Simulator rules' ? 'Simulator rules' : report.status}</small></span>
    <Handle type="source" position={Position.Bottom} style={{ opacity: 0 }} />
  </button>
}

const H = () => (
  <>
    <Handle type="target" position={Position.Left} style={{ opacity: 0 }} />
    <Handle type="source" position={Position.Right} style={{ opacity: 0 }} />
  </>
)


// ==================== Unmistakable Equipment Sprites ====================

// 1. DATA CENTER SERVER POD (Origin of Chain)
function DataCenterSprite() {
  return (
    <div className="node-sprite-wrapper dc-sprite" title="Data Center Server Rack (Origin of IT Heat Load)">
      <svg viewBox="0 0 32 36" width="32" height="36" fill="none" aria-hidden="true">
        {/* Outer Server Cabinet Rack */}
        <rect x="3" y="2" width="26" height="32" rx="3" fill="#0f172a" stroke="#38bdf8" strokeWidth="1.5" />
        {/* Top ventilation louvers */}
        <line x1="7" y1="5" x2="25" y2="5" stroke="#475569" strokeWidth="1" />
        <line x1="7" y1="7" x2="25" y2="7" stroke="#475569" strokeWidth="1" />
        {/* Blade Server 1 */}
        <rect x="6" y="10" width="20" height="5" rx="1" fill="#1e293b" stroke="#334155" strokeWidth="1" />
        <circle cx="9" cy="12.5" r="1" fill="#22c55e" className="led-blink" />
        <line x1="13" y1="12.5" x2="23" y2="12.5" stroke="#64748b" strokeWidth="1" strokeDasharray="2 2" />
        {/* Blade Server 2 */}
        <rect x="6" y="17" width="20" height="5" rx="1" fill="#1e293b" stroke="#334155" strokeWidth="1" />
        <circle cx="9" cy="19.5" r="1" fill="#22c55e" className="led-blink" style={{ animationDelay: '0.4s' }} />
        <line x1="13" y1="19.5" x2="23" y2="19.5" stroke="#64748b" strokeWidth="1" strokeDasharray="2 2" />
        {/* Blade Server 3 */}
        <rect x="6" y="24" width="20" height="5" rx="1" fill="#1e293b" stroke="#334155" strokeWidth="1" />
        <circle cx="9" cy="26.5" r="1" fill="#38bdf8" className="led-blink" style={{ animationDelay: '0.8s' }} />
        <line x1="13" y1="26.5" x2="23" y2="26.5" stroke="#64748b" strokeWidth="1" strokeDasharray="2 2" />
      </svg>
    </div>
  )
}

// 2. THERMAL STORAGE RESERVOIR (Buffer Tank)
function TankVesselSprite({ levelPct = 60 }: { levelPct?: number }) {
  return (
    <div className="node-sprite-wrapper tank-sprite" title="Chilled Water Thermal Storage Vessel">
      <svg viewBox="0 0 28 32" width="28" height="32" fill="none" aria-hidden="true">
        {/* Cylindrical tank body with rounded dome caps */}
        <path d="M4 8C4 5.5 8 4 14 4C20 4 24 5.5 24 8V24C24 26.5 20 28 14 28C8 28 4 26.5 4 24V8Z" fill="#0f172a" stroke="#60a5fa" strokeWidth="1.5" />
        {/* Upper inspection dome seam */}
        <ellipse cx="14" cy="8" rx="10" ry="3.5" fill="#1e293b" stroke="#38bdf8" strokeWidth="1" />
        {/* Liquid level fill interior */}
        <clipPath id="tankBodyClip">
          <path d="M4 8C4 5.5 8 4 14 4C20 4 24 5.5 24 8V24C24 26.5 20 28 14 28C8 28 4 26.5 4 24V8Z" />
        </clipPath>
        <g clipPath="url(#tankBodyClip)">
          <rect x="4" y={28 - (levelPct * 0.2)} width="20" height="24" fill="url(#tankLiquidGrad)" opacity="0.8" />
        </g>
        <defs>
          <linearGradient id="tankLiquidGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" />
            <stop offset="100%" stopColor="#1d4ed8" />
          </linearGradient>
        </defs>
      </svg>
    </div>
  )
}

// 3. CENTRIFUGAL CHILLER PUMP (Rotating Impeller)
function ChillerPumpSprite({ isRunning = false, isTripped = false }: { isRunning?: boolean; isTripped?: boolean }) {
  const spinClass = isTripped ? 'impeller-tripped' : isRunning ? 'impeller-running' : 'impeller-stopped'
  return (
    <div className="node-sprite-wrapper pump-sprite" title="Centrifugal Chiller Circulation Pump">
      <svg viewBox="0 0 32 32" width="30" height="30" fill="none" aria-hidden="true">
        {/* Volute outer spiral casing */}
        <circle cx="16" cy="16" r="14" fill="#0f172a" stroke={isTripped ? '#ef4444' : isRunning ? '#22c55e' : '#64748b'} strokeWidth="2" />
        {/* Discharge pipe flange */}
        <path d="M26 6L30 2" stroke={isTripped ? '#ef4444' : isRunning ? '#22c55e' : '#64748b'} strokeWidth="2.5" strokeLinecap="round" />
        {/* 4-Blade Impeller Rotor */}
        <g className={`impeller-rotor ${spinClass}`}>
          <circle cx="16" cy="16" r="3" fill="#cbd5e1" />
          {/* Vane 1 */}
          <path d="M16 13C16 8 20 7 21 8C20 11 18 13 16 13Z" fill={isTripped ? '#ef4444' : '#38bdf8'} />
          {/* Vane 2 */}
          <path d="M19 16C24 16 25 20 24 21C21 20 19 18 19 16Z" fill={isTripped ? '#ef4444' : '#38bdf8'} />
          {/* Vane 3 */}
          <path d="M16 19C16 24 12 25 11 24C12 21 14 19 16 19Z" fill={isTripped ? '#ef4444' : '#38bdf8'} />
          {/* Vane 4 */}
          <path d="M13 16C8 16 7 12 8 11C11 12 13 14 13 16Z" fill={isTripped ? '#ef4444' : '#38bdf8'} />
        </g>
      </svg>
    </div>
  )
}

// 4. CHILLED WATER DISTRIBUTION LOOP (Pipeline Header)
function PipelineHeaderSprite() {
  return (
    <div className="node-sprite-wrapper pipe-sprite" title="Dual Chilled-Water Distribution Header">
      <svg viewBox="0 0 28 28" width="26" height="26" fill="none" aria-hidden="true">
        {/* Supply Pipe */}
        <rect x="2" y="5" width="24" height="6" rx="2" fill="#1e293b" stroke="#38bdf8" strokeWidth="1.5" />
        <path d="M8 8L12 8M16 8L20 8" stroke="#38bdf8" strokeWidth="1.5" strokeLinecap="round" />
        {/* Return Pipe */}
        <rect x="2" y="17" width="24" height="6" rx="2" fill="#1e293b" stroke="#818cf8" strokeWidth="1.5" />
        <path d="M20 20L16 20M12 20L8 20" stroke="#818cf8" strokeWidth="1.5" strokeLinecap="round" />
        {/* Cross Connection Flange */}
        <line x1="14" y1="11" x2="14" y2="17" stroke="#475569" strokeWidth="2" strokeDasharray="2 2" />
      </svg>
    </div>
  )
}

// 5. EVAPORATIVE COOLING TOWER (Terminus of Chain)
function CoolingTowerSprite() {
  return (
    <div className="node-sprite-wrapper tower-sprite" title="Evaporative Cooling Tower (Atmospheric Heat Rejection)">
      <svg viewBox="0 0 32 36" width="32" height="36" fill="none" aria-hidden="true">
        {/* Rising heat vapor plumes */}
        <path d="M11 7C10 4 12 3 11 1" stroke="#38bdf8" strokeWidth="1.2" strokeLinecap="round" className="vapor-plume" />
        <path d="M16 7C15 3 17 2 16 0" stroke="#93c5fd" strokeWidth="1.2" strokeLinecap="round" className="vapor-plume" style={{ animationDelay: '0.4s' }} />
        <path d="M21 7C20 4 22 3 21 1" stroke="#38bdf8" strokeWidth="1.2" strokeLinecap="round" className="vapor-plume" style={{ animationDelay: '0.8s' }} />
        {/* Hyperbolic cooling tower chimney structure */}
        <path d="M8 32L11 9H21L24 32C19 33.5 13 33.5 8 32Z" fill="#0f172a" stroke="#38bdf8" strokeWidth="1.5" />
        {/* Top induced draft fan rim */}
        <ellipse cx="16" cy="9" rx="5" ry="1.8" fill="#1e293b" stroke="#60a5fa" strokeWidth="1" />
        {/* Internal fan blade icon */}
        <circle cx="16" cy="9" r="1.2" fill="#38bdf8" />
        {/* Lower air intake louvers */}
        <line x1="9" y1="26" x2="23" y2="26" stroke="#475569" strokeWidth="1" />
        <line x1="8.5" y1="29" x2="23.5" y2="29" stroke="#475569" strokeWidth="1" />
      </svg>
    </div>
  )
}

function SourceNode({ data }: NodeProps<Node<D>>) {
  const s = data.env.state.sources[data.node.id]
  return (
    <div className={`nd source dc-node ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="node-chain-bookend origin-tag">ORIGIN</div>
      <div className="node-sprite-row">
        <DataCenterSprite />
        <div className="node-header-text">
          <b>{data.node.id}</b>
          <div className="asset-purpose">DATA CENTER · IT POD</div>
        </div>
      </div>
      <div className="sub">{s.flow.toFixed(0)} kW Heat Load</div>
      {s.eff_rate > s.rate && <div className="badge warn">surge ×{(s.eff_rate / s.rate).toFixed(2)}</div>}
      {s.curtailment_pct > 0 && <div className="badge">cut {s.curtailment_pct.toFixed(0)}%</div>}
      {s.shut_in && <div className="badge crit" title="HH thermal protection: IT load shed">LOAD SHED {Number(s.shed_pct ?? 100).toFixed(0)}%</div>}
    </div>
  )
}

function TankNode({ data }: NodeProps<Node<D>>) {
  const t = data.env.state.tanks[data.node.id]
  const lim = data.network.config.limits
  const forecast = data.env.forecast.tanks[data.node.id]
  const highHigh = forecast?.time_to_HH
  const remaining = highHigh == null ? null : Math.max(0, highHigh - Math.max(0, data.env.state.t_min - data.env.forecast.as_of_min))
  const pct = (v: number) => `${Math.min(100, (v / t.capacity) * 100)}%`
  const levelNum = Math.min(100, (t.volume / (t.capacity || 1)) * 100)
  return (
    <div className={`nd tank st-${t.status} ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="node-sprite-row">
        <TankVesselSprite levelPct={levelNum} />
        <div className="node-header-text">
          <div className="tank-head"><b>{data.node.id}</b><span>{t.volume.toFixed(0)} kWh</span></div>
          <div className="asset-purpose">{t.role === 'buffer' ? 'THERMAL BUFFER TANK' : 'HALL THERMAL MASS'}</div>
        </div>
      </div>
      <div className="bar">
        <div className="fill" style={{ height: pct(t.volume) }} />
        <div className="mark" style={{ bottom: pct(lim.H) }}><i>H</i></div>
        <div className="mark hh" style={{ bottom: pct(lim.HH) }}><i>HH</i></div>
      </div>
      <div className="tank-readings"><span>{Math.max(0, t.capacity - t.volume).toFixed(0)} kWh free</span><span title={`Forecast at T+${data.env.forecast.as_of_min} min`}>{remaining == null ? 'No HH forecast' : `HH in ${Math.ceil(remaining)} min`}</span></div>
      <div className="sub">In {t.inflow.toFixed(0)} / out {t.outflow.toFixed(0)} kW</div>
      {t.interlock.tripped && <div className="badge crit">INTERLOCK TRIP</div>}
      {t.interlock.ll_tripped && <div className="badge crit">LL trip</div>}
      {t.overflow_bbl > 0 && <div className="badge crit">THERMAL EVENT {t.overflow_bbl.toFixed(0)} kWh</div>}
    </div>
  )
}


function PumpNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.pumps[data.node.id]
  const cls = !p.available ? 'unavail' : p.run_state === 'RUNNING' ? 'running' : p.run_state === 'STARTING' ? 'starting' : p.run_state === 'TRIPPED' ? 'tripped' : 'stopped'
  const d = p.diagnosis
  const isRunning = p.run_state === 'RUNNING'
  const isTripped = p.run_state === 'TRIPPED'
  return (
    <div className={`nd pump-wrap ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="pump-node-box">
        <div className="node-sprite-row">
          <ChillerPumpSprite isRunning={isRunning} isTripped={isTripped} />
          <div className="node-header-text">
            <b>{data.node.id.replace('CHP-', 'CHILLER ')}</b>
            <div className="asset-purpose">CENTRIFUGAL PUMP</div>
          </div>
        </div>
        <div className={`pump ${cls}`} title={`${p.run_state}${p.limited_by ? ` (limited by ${p.limited_by})` : ''} · double-click for detail`}>
          {data.node.id.replace('CHP-', 'CH')}
          <button className="info nodrag" title="Pump detail" aria-label={`View ${data.node.id} details`} onClick={(e) => { e.stopPropagation(); data.onDetails?.(data.node.id) }}>ⓘ</button>
        </div>
        <div className="sub">{!p.available ? 'UNAVAILABLE' : p.run_state === 'STOPPED' && p.role === 'standby' ? 'STANDBY' : p.run_state}</div>
        {d?.w_est != null && (
          <div className={`badge ${d.code === 'NONE' ? '' : 'warn'}`} title={d.text}>
            w {(d.w_est * 100).toFixed(0)}% {d.code !== 'NONE' ? 'FAULT' : ''}
          </div>
        )}
        {p.auto_started && <div className="badge">AUTO</div>}
      </div>
    </div>
  )
}

function PipeNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.pipelines[data.node.id]
  const util = p.cap > 0 ? p.flow / p.cap : 0
  return (
    <div className={`nd pipe ${util > 0.98 ? 'st-warning' : ''} ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="node-sprite-row">
        <PipelineHeaderSprite />
        <div className="node-header-text">
          <b>{data.node.label}</b>
          <div className="asset-purpose">CHILLED-WATER LOOP</div>
        </div>
      </div>
      <div className="sub">{p.flow.toFixed(0)} / {p.cap.toFixed(0)} kW</div>
      {p.r > 1 && <div className="badge warn">restricted r={p.r.toFixed(1)}</div>}
    </div>
  )
}

function TreatNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.treatment[data.node.id]
  return (
    <div className={`nd treat tower-node ${p.flow >= p.cap - FLOW_EPS ? 'st-warning' : ''} ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="node-chain-bookend terminus-tag">TERMINUS</div>
      <div className="node-sprite-row">
        <CoolingTowerSprite />
        <div className="node-header-text">
          <b>{data.node.label}</b>
          <div className="asset-purpose">COOLING TOWER · HEAT REJECTION</div>
        </div>
      </div>
      <div className="sub">{p.flow.toFixed(0)} / {p.cap.toFixed(0)} kW</div>
      {p.intake_factor < 1 && <div className="badge warn">constrained {(p.intake_factor * 100).toFixed(0)}%</div>}
    </div>
  )
}

const nodeTypes = { source: SourceNode, tank: TankNode, pump: PumpNode, pipeline: PipeNode, treatment: TreatNode, investigator: InvestigationNode }

function edgeFlow(env: Envelope, from: string, to: string, fromKind: string): number {
  const s = env.state
  if (fromKind === 'source') return s.sources[from].flow
  if (fromKind === 'tank') return s.pumps[to]?.flow ?? 0
  if (fromKind === 'pump') return s.pumps[from].flow
  if (fromKind === 'pipeline') return s.pipelines[from].flow
  return 0
}

export function NetworkDiagram({ env, network, onPumpDetail, incidentAssets = [], intelligence }: { env: Envelope; network: Network; onPumpDetail: (id: string) => void; incidentAssets?: string[]; intelligence?: AgentState | null }) {
  const [showAgents, setShowAgents] = useState(true)
  const [selectedRole, setSelectedRole] = useState<string | null>(null)
  const team = intelligence?.enabled ? intelligence.team : null
  const reports = showAgents ? team?.reports ?? [] : []
  const selectedReport = reports.find(r => r.role === selectedRole)
  // React Flow clears handle bounds when controlled nodes lose `measured`.
  // Carry dimensions across telemetry updates so edges are not unmounted.
  const [dimensions, setDimensions] = useState<Record<string, { width: number; height: number }>>({})
  const onNodesChange = useCallback((changes: NodeChange<Node<D>>[]) => {
    setDimensions(previous => {
      let next = previous
      for (const change of changes) {
        if (change.type !== 'dimensions' || !change.dimensions) continue
        const current = previous[change.id]
        if (current?.width === change.dimensions.width && current?.height === change.dimensions.height) continue
        if (next === previous) next = { ...previous }
        next[change.id] = change.dimensions
      }
      return next
    })
  }, [])
  const container = useRef<HTMLDivElement>(null)
  const refit = useRef<() => void>(() => {})
  useEffect(() => {
    const timer = window.setTimeout(() => refit.current(), 160)
    return () => window.clearTimeout(timer)
  }, [reports.length])
  useEffect(() => {
    let timer: number
    const observer = new ResizeObserver(([entry]) => {
      window.clearTimeout(timer)
      if (entry.contentRect.width) timer = window.setTimeout(() => refit.current(), 120)
    })
    observer.observe(container.current!)
    return () => { observer.disconnect(); window.clearTimeout(timer) }
  }, [])
  const [focus, setFocus] = useState<{ id: string; related: Set<string> } | null>(null)

  const kinds = useMemo(() => Object.fromEntries(network.topology.nodes.map((n) => [n.id, n.type])), [network])
  const inFocus = (id: string) => selectedReport ? selectedReport.focus_asset_ids.includes(id) : !focus || focus.id === id || focus.related.has(id)

  const nodes: Node<D>[] = network.topology.nodes.map((n) => ({
    id: n.id, type: n.type, draggable: false, measured: dimensions[n.id],
    className: incidentAssets.includes(n.id) ? 'incident-node' : '',
    position: { x: n.ui.col * COL_W, y: n.ui.row * ROW_H },
    data: { node: n, env, network, dim: !inFocus(n.id), onDetails: onPumpDetail },
  }))
  const edges: Edge[] = network.topology.edges.map((e) => {
    const transfer = e.kind === 'transfer'
    const flow = transfer ? 0 : edgeFlow(env, e.from, e.to, kinds[e.from])
    const live = flow > FLOW_EPS
    const dim = !(inFocus(e.from) && inFocus(e.to))
    const affected = !transfer && incidentAssets.includes(e.from) && incidentAssets.includes(e.to)
    return {
      id: `${e.from}-${e.to}`, source: e.from, target: e.to,
      className: transfer ? undefined : `plant-flow-edge ${live ? 'flow-live' : ''}`,
      label: transfer ? 'buffer transfer' : live ? `${flow.toFixed(0)} kW` : undefined,
      style: { stroke: affected ? 'var(--warn)' : live ? 'var(--flow)' : 'var(--idle)', strokeWidth: affected ? 3 : live ? 2.5 : 1.5, strokeDasharray: live ? undefined : '5 5', opacity: dim ? 0.2 : live ? 1 : 0.6 },
      labelStyle: { fill: 'var(--text)', fontSize: 11 }, labelBgStyle: { fill: 'var(--panel)' },
    }
  })

  reports.forEach((report, index) => {
    const id = `agent:${report.role}`
    const working = report.status === 'Reviewing'
    nodes.push({ id, type: 'investigator', position: { x: index * 290, y: -145 }, draggable: false,
      measured: dimensions[id], data: { node: {}, env, network, dim: false, report, selected: selectedRole === report.role,
        select: () => { setSelectedRole(selectedRole === report.role ? null : report.role); setFocus(null) } } })
    if (index < reports.length - 1) edges.push({ id: `${id}:handoff`, source: id, target: `agent:${reports.at(-1)!.role}`,
      type: 'smoothstep', className: `investigation-link handoff ${working ? 'is-working' : ''}`,
      style: { stroke: 'var(--agent-line)', strokeWidth: 1, opacity: report.status === 'Delivered' ? .65 : .2 } })
    if (working || selectedRole === report.role) report.focus_asset_ids.forEach(asset => {
      if (!network.topology.nodes.some(n => n.id === asset)) return
      edges.push({ id: `${id}:${asset}`, source: id, target: asset, type: 'smoothstep',
        className: `investigation-link ${working ? 'is-working' : ''}`,
        style: { stroke: 'var(--agent-line)', strokeWidth: 1, opacity: working ? .5 : .3 } })
    })
  })

  const onClick = (_: unknown, n: Node) => {
    if (n.type === 'investigator') return
    setSelectedRole(null)
    if (focus?.id === n.id) return setFocus(null)
    api.impact(n.id).then((r) => setFocus({ id: n.id, related: new Set([...r.upstream, ...r.downstream]) }))
  }

  return (
    <div ref={container} className="investigation-canvas" style={{ height: '100%', width: '100%' }}>
      <div className="investigation-toolbar"><button aria-pressed={showAgents} onClick={() => { setShowAgents(!showAgents); setSelectedRole(null) }}>Agent layer <span>{showAgents ? 'On' : 'Off'}</span></button>{team && showAgents && <span>Observed T+{team.t_min} min{env.state.t_min > team.t_min ? ' · Earlier snapshot' : ''}</span>}</div>
      <ReactFlow nodes={nodes} onNodesChange={onNodesChange} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.15 }}
      onInit={view => { refit.current = () => { void view.fitView({padding: 0.1}) } }}
      nodesConnectable={false} proOptions={{ hideAttribution: true }} onNodeClick={onClick} onPaneClick={() => { setFocus(null); setSelectedRole(null) }}
      minZoom={0.3} colorMode="dark" zoomOnDoubleClick={false}
      onNodeDoubleClick={(_, n) => { if (n.type === 'pump') onPumpDetail(n.id) }}>
      <Background gap={24} />
    </ReactFlow>
    {selectedReport && <section className="graph-agent-report" aria-label={`${selectedReport.role} graph findings`}>
      <header><strong>{selectedReport.role}</strong><button aria-label="Close agent findings" onClick={() => setSelectedRole(null)}>×</button></header>
      <small>{selectedReport.source ?? selectedReport.status} · T+{team!.t_min} min</small>
      <p>{selectedReport.interpretations[0]?.text ?? selectedReport.observation ?? 'Awaiting specialist handoffs.'}</p>
      <details><summary>Tool calls · {selectedReport.tool_events.length}</summary>{selectedReport.tool_events.map((event, i) => <div className="graph-tool" key={i}><code>{event.tool}</code><span>{event.status}</span>{event.origin && <small>{event.origin}</small>}{event.evidence_ids.map(id => intelligence?.evidence[id] && <span key={id}>{eventText(intelligence.evidence[id].label)}</span>)}</div>)}</details>
    </section>}
    </div>
  )
}
