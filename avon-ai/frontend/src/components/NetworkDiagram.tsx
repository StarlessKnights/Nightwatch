import { useEffect, useMemo, useRef, useState } from 'react'
import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { api } from '../api'
import type { Envelope, Network } from '../types'

const COL_W = 230
const ROW_H = 120
const FLOW_EPS = 0.5 // bbl/hr below which an edge is drawn as "no flow"

type D = { node: any; env: Envelope; network: Network; dim: boolean }

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
      <b>{data.node.label}</b>
      <div className="sub">{s.flow.toFixed(0)} bbl/hr</div>
      {s.eff_rate > s.rate && <div className="badge warn">surge ×{(s.eff_rate / s.rate).toFixed(2)}</div>}
      {s.curtailment_pct > 0 && <div className="badge">cut {s.curtailment_pct.toFixed(0)}%</div>}
      {s.shut_in && <div className="badge crit" title="HH interlock: inflow shut in">🔒 SHUT IN</div>}
    </div>
  )
}

function TankNode({ data }: NodeProps<Node<D>>) {
  const t = data.env.state.tanks[data.node.id]
  const lim = data.network.config.limits
  const pct = (v: number) => `${Math.min(100, (v / t.capacity) * 100)}%`
  return (
    <div className={`nd tank st-${t.status} ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className="tank-head"><b>{data.node.label}</b><span>{t.volume.toFixed(0)} bbl</span></div>
      <div className="bar">
        <div className="fill" style={{ height: pct(t.volume) }} />
        <div className="mark" style={{ bottom: pct(lim.H) }}><i>H</i></div>
        <div className="mark hh" style={{ bottom: pct(lim.HH) }}><i>HH</i></div>
      </div>
      <div className="sub">in {t.inflow.toFixed(0)} / out {t.outflow.toFixed(0)}</div>
      {t.interlock.tripped && <div className="badge crit">🔒 HH interlock</div>}
      {t.interlock.ll_tripped && <div className="badge crit">LL trip</div>}
      {t.overflow_bbl > 0 && <div className="badge crit">OVERFLOW {t.overflow_bbl.toFixed(0)} bbl</div>}
    </div>
  )
}

function PumpNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.pumps[data.node.id]
  const cls = !p.available ? 'unavail' : p.run_state === 'RUNNING' ? 'running' : p.run_state === 'STARTING' ? 'starting' : p.run_state === 'TRIPPED' ? 'tripped' : 'stopped'
  return (
    <div className={`nd pump-wrap ${data.dim ? 'dim' : ''}`}>
      <H />
      <div className={`pump ${cls}`} title={`${p.run_state}${p.limited_by ? ` (limited by ${p.limited_by})` : ''}`}>{data.node.id.replace('P-', 'P')}</div>
      <div className="sub">{!p.available ? 'UNAVAILABLE' : p.run_state === 'STOPPED' && p.role === 'standby' ? 'STANDBY' : p.run_state}</div>
      {p.eff_capacity_factor < 0.995 && <div className="badge warn">{(p.eff_capacity_factor * 100).toFixed(0)}%</div>}
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
      <div className="sub">{p.flow.toFixed(0)} / {p.cap.toFixed(0)} bbl/hr</div>
      {p.restriction_factor < 1 && <div className="badge warn">restricted {(p.restriction_factor * 100).toFixed(0)}%</div>}
    </div>
  )
}

function TreatNode({ data }: NodeProps<Node<D>>) {
  const p = data.env.state.treatment[data.node.id]
  return (
    <div className={`nd treat ${p.flow >= p.cap - FLOW_EPS ? 'st-warning' : ''} ${data.dim ? 'dim' : ''}`}>
      <H />
      <b>{data.node.label}</b>
      <div className="sub">{p.flow.toFixed(0)} / {p.cap.toFixed(0)} bbl/hr</div>
      {p.intake_factor < 1 && <div className="badge warn">constrained {(p.intake_factor * 100).toFixed(0)}%</div>}
    </div>
  )
}

const nodeTypes = { source: SourceNode, tank: TankNode, pump: PumpNode, pipeline: PipeNode, treatment: TreatNode }

function edgeFlow(env: Envelope, from: string, to: string, fromKind: string): number {
  const s = env.state
  if (fromKind === 'source') return s.sources[from].flow
  if (fromKind === 'tank') return s.pumps[to]?.flow ?? 0
  if (fromKind === 'pump') return s.pumps[from].flow
  if (fromKind === 'pipeline') return s.pipelines[from].flow
  return 0
}

export function NetworkDiagram({ env, network, incidentAssets = [] }: { env: Envelope; network: Network; incidentAssets?: string[] }) {
  const container = useRef<HTMLDivElement>(null)
  const refit = useRef<() => void>(() => {})
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
  const inFocus = (id: string) => !focus || focus.id === id || focus.related.has(id)

  const nodes: Node<D>[] = network.topology.nodes.map((n) => ({
    id: n.id, type: n.type, draggable: false,
    className: incidentAssets.includes(n.id) ? 'incident-node' : '',
    position: { x: n.ui.col * COL_W, y: n.ui.row * ROW_H },
    data: { node: n, env, network, dim: !inFocus(n.id) },
  }))
  const edges: Edge[] = network.topology.edges.map((e) => {
    const transfer = e.kind === 'transfer'
    const flow = transfer ? 0 : edgeFlow(env, e.from, e.to, kinds[e.from])
    const live = flow > FLOW_EPS
    const dim = !(inFocus(e.from) && inFocus(e.to))
    const affected = !transfer && incidentAssets.includes(e.from) && incidentAssets.includes(e.to)
    return {
      id: `${e.from}-${e.to}`, source: e.from, target: e.to, animated: live,
      label: transfer ? 'buffer transfer' : live ? `${flow.toFixed(0)} bbl/hr` : undefined,
      style: { stroke: affected ? 'var(--warn)' : live ? 'var(--flow)' : 'var(--idle)', strokeWidth: affected ? 3 : live ? 2.5 : 1.5, strokeDasharray: live ? undefined : '5 5', opacity: dim ? 0.2 : live ? 1 : 0.6 },
      labelStyle: { fill: 'var(--text)', fontSize: 11 }, labelBgStyle: { fill: 'var(--panel)' },
    }
  })

  const onClick = (_: unknown, n: Node) => {
    if (focus?.id === n.id) return setFocus(null)
    api.impact(n.id).then((r) => setFocus({ id: n.id, related: new Set([...r.upstream, ...r.downstream]) }))
  }

  return (
    <div ref={container} style={{ height: '100%', width: '100%' }}><ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.1 }}
      onInit={view => { refit.current = () => { void view.fitView({padding: 0.1}) } }}
      nodesConnectable={false} proOptions={{ hideAttribution: true }} onNodeClick={onClick} onPaneClick={() => setFocus(null)}
      minZoom={0.3} colorMode="dark">
      <Background gap={24} />
    </ReactFlow></div>
  )
}
