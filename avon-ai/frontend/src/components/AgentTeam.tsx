import { useState } from 'react'
import type { AgentState, TeamReport } from '../agentTypes'
import { evidenceLabel } from '../evidenceFormat'
import { OperatorDialog } from './OperatorDialog'
import './agentTeam.css'

const descriptions: Record<string, string> = {
  'Thermal Load Monitor': 'Heat balance and cooling restrictions',
  'Cooling Plant Monitor': 'Chiller health and N+1 readiness',
  Coordinator: 'Operator briefing',
}

function modelLabel(model: string) {
  if (model === 'nvidia/nemotron-3.5-lightning-30b-a3b') return 'Lightning · 30B / 3B active'
  if (model === 'nvidia/nemotron-3.5-super-vl-120b-a12b') return 'Super VL · 120B / 12B active'
  return model
}

function TeamNode({ report, selected, select }: { report: TeamReport; selected: boolean; select: () => void }) {
  return <button type="button" className="team-node" aria-pressed={selected} onClick={select}>
    <strong>{report.role}</strong>
    <small>{descriptions[report.role]}</small>
    <span className={'team-stage ' + (report.status === 'Reviewing' ? 'working' : report.source ? 'done' : '')}>
      {report.status}
    </span>
  </button>
}

export function AgentTeam({ data, inspect, ask }: { data: AgentState; inspect: (id: string) => void; ask: () => void }) {
  const [selected, setSelected] = useState('Coordinator')
  const [expanded, expand] = useState(false)
  const team = data.team
  if (!team) return <p className="agent-empty">{data.enabled ? 'Waiting for the first plant observation…' : 'Enable Intelligence to start the agent team.'}</p>
  const coordinator = team.reports.find(r => r.role === 'Coordinator')!
  const report = team.reports.find(r => r.role === selected) ?? coordinator
  const refs = (ids: string[]) => <div className="evidence-links">{ids.map(id => data.evidence[id] &&
    <button key={id} onClick={() => inspect(id)}>{evidenceLabel(data.evidence[id])}</button>)}</div>
  const view = <div className="team-view">
    <header><h3>Agent team</h3><span>T+{team.t_min} min</span>{!expanded && <button onClick={() => expand(true)}>Expand ↗</button>}</header>
    <p className="team-trigger">{team.trigger}</p>
    <div className="team-diagram" aria-label="Specialist reports flow to the Coordinator">
      <div className="team-specialists">{team.reports.filter(r => r !== coordinator).map(r =>
        <TeamNode key={r.role} report={r} selected={report === r} select={() => setSelected(r.role)}/>)}</div>
      <div className="team-branches" aria-hidden="true">{team.reports.filter(r => r !== coordinator).map(r =>
        <i key={r.role} className={r.status === 'Delivered' ? 'delivered' : ''}/>)}</div>
      <div className="team-lead"><TeamNode report={coordinator} selected={report === coordinator} select={() => setSelected(coordinator.role)}/></div>
    </div>
    <section className="team-report" aria-label={report.role + ' findings'}>
      <header><h4>{report.role}</h4><span>{report.source ?? report.status}</span></header>
      <small title={report.model}>Assigned model · {modelLabel(report.model)}</small>
      <p>{report.observation || 'The Coordinator will review both specialist handoffs.'}</p>
      {report.interpretations.map((finding,i) => <div className="team-finding" key={i}>{finding.text}{refs(finding.evidence_ids)}</div>)}
      {report.error && <p className="hint">{report.error}</p>}
      {report.evidence_ids.length > 0 && <details><summary>Source readings ({report.evidence_ids.length})</summary>{refs(report.evidence_ids)}</details>}
    </section>
    <details className="team-trace"><summary>Handoff history ({team.events.length})</summary>
      {team.events.map((event,i) => <div key={i}><time>+{event.elapsed_s}s</time><span>{event.role} · {event.status}{event.source && ' · ' + event.source}</span></div>)}
    </details>
    <button className="case-link" onClick={ask}>Ask the Coordinator ↗</button>
  </div>
  return expanded ? <OperatorDialog title="Agent investigation" close={() => expand(false)}>{view}</OperatorDialog> : view
}
