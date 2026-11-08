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

function SourceNode({ data }: NodeProps<Node<D>>) {
  const s = data.env.state.sources[data.node.id]
  return (
    <div className={`nd source ${data.dim ? 'dim' : ''}`}>
      <H />
      <b>{data.node.id}</b>
      <div className="asset-purpose">IT heat load</div>
      <div className="sub">{s.flow.toFixed(0)} kW</div>
      {s.eff_rate > s.rate && <div className="badge warn">surge ×{(s.eff_rate / s.rate).toFixed(2)}</div>}
      {s.curtailment_pct > 0 && <div className="badge">cut {s.curtailment_pct.toFixed(0)}%</div>}
      {s.shut_in && <div className="badge crit" title="HH thermal protection: IT load shed">🔒 LOAD SHED {Number(s.shed_pct ?? 100).toFixed(0)}%</div>}
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
  return (
    <div className={`nd tank st-${t.status} ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="tank-head"><b>{data.node.id}</b><span>{t.volume.toFixed(0)} kWh</span></div>
      <div className="asset-purpose">{t.role === 'buffer' ? 'Thermal storage' : 'Hall thermal mass'}</div>
      <div className="bar">
        <div className="fill" style={{ height: pct(t.volume) }} />
        <div className="mark" style={{ bottom: pct(lim.H) }}><i>H</i></div>
        <div className="mark hh" style={{ bottom: pct(lim.HH) }}><i>HH</i></div>
      </div>
      <div className="tank-readings"><span>{Math.max(0, t.capacity - t.volume).toFixed(0)} kWh free</span><span title={`Forecast at T+${data.env.forecast.as_of_min} min`}>{remaining == null ? 'No HH forecast' : `HH in ${Math.ceil(remaining)} min`}</span></div>
      <div className="sub">In {t.inflow.toFixed(0)} / out {t.outflow.toFixed(0)} kW</div>
      {t.interlock.tripped && <div className="badge crit">🔒 HH protection</div>}
      {t.interlock.ll_tripped && <div className="badge crit">LL trip</div>}
      {t.overflow_bbl > 0 && <div className="badge crit">THERMAL EVENT {t.overflow_bbl.toFixed(0)} kWh</div>}
    </div>
  )
}

const DIAG_ICON: Record<string, string> = { PUMP_WEAR: '🔧', RESTRICTION: '🚧', COMPOUND: '⚠' }

function PumpNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.pumps[data.node.id]
  const cls = !p.available ? 'unavail' : p.run_state === 'RUNNING' ? 'running' : p.run_state === 'STARTING' ? 'starting' : p.run_state === 'TRIPPED' ? 'tripped' : 'stopped'
  const d = p.diagnosis
  return (
    <div className={`nd pump-wrap ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className={`pump ${cls}`} title={`${p.run_state}${p.limited_by ? ` (limited by ${p.limited_by})` : ''} · double-click for detail`}>
        {data.node.id.replace('CHP-', 'CH')}
        <button className="info nodrag" title="Pump detail" aria-label={`View ${data.node.id} details`} onClick={(e) => { e.stopPropagation(); data.onDetails?.(data.node.id) }}>ⓘ</button>
      </div>
      <div className="sub">{!p.available ? 'UNAVAILABLE' : p.run_state === 'STOPPED' && p.role === 'standby' ? 'STANDBY' : p.run_state}</div>
      {d?.w_est != null && (
        <div className={`badge ${d.code === 'NONE' ? '' : 'warn'}`} title={d.text}>
          w {(d.w_est * 100).toFixed(0)}% {DIAG_ICON[d.code] ?? ''}
        </div>
      )}
      {p.auto_started && <div className="badge">AUTO</div>}
    </div>
  )
}

function PipeNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.pipelines[data.node.id]
  const util = p.cap > 0 ? p.flow / p.cap : 0
  return (
    <div className={`nd pipe ${util > 0.98 ? 'st-warning' : ''} ${data.dim ? 'dim' : ''}`}>
      <H />
      <b>{data.node.label}</b>
      <div className="asset-purpose">Chilled-water loop</div>
      <div className="sub">{p.flow.toFixed(0)} / {p.cap.toFixed(0)} kW</div>
      {p.r > 1 && <div className="badge warn">restricted r={p.r.toFixed(1)}</div>}
    </div>
  )
}

function TreatNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.treatment[data.node.id]
  return (
    <div className={`nd treat ${p.flow >= p.cap - FLOW_EPS ? 'st-warning' : ''} ${data.dim ? 'dim' : ''}`}>
      <H />
      <b>{data.node.label}</b>
      <div className="asset-purpose">Heat rejection</div>
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
