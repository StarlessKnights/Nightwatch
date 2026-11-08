import { useEffect, useState } from 'react'
import type { AgentState, Evidence, Interpretation, SourceRecord } from '../agentTypes'
import { money } from '../format'
import { agentCall } from '../useAgent'

import { evidenceLabel } from '../evidenceFormat'
import { EvidenceViewer, SourceTimeline } from './EvidenceViewer'
import { ShiftDesk, ScenarioCompare, WhatIfLab } from './ShiftDesk'
import { AgentTeam } from './AgentTeam'

interface Props {
  data: AgentState | null; error: string | null
  run: (path: string, body: unknown) => Promise<boolean>
  onFocus: (assets: string[]) => void; assets: string[]
}
type History = { coverage: string; signals: { asset_id: string; observed_fault_events: number; interpretation: string; sources: SourceRecord[] }[]; notes: { id: string; run_id: string; at: string; data: { asset_id: string; text: string; provenance: string } }[] }

export function IntelligencePanel({ data, error, run, onFocus, assets }: Props) {
  const [tab, setTab] = useState('Agents')
  const [notesSaved, setNotesSaved] = useState(0)
  const [input, setInput] = useState('')
  const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [history, setHistory] = useState<History | null>(null)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [asset, setAsset] = useState(assets[0] ?? '')
  const latestActivity = data?.activity.at(-1)?.id
  useEffect(() => {
    let active = true
    if (tab === 'History') agentCall<History>('/history').then((value) => { if (active) { setHistory(value); setHistoryError(null) } }).catch((e) => { if (active) setHistoryError(String(e)) })
    return () => { active = false }
  }, [tab, data?.run_id, latestActivity, notesSaved])
  if (!data) return <div className="panel-fill"><h3>AVON Intelligence</h3><p className="hint">{error ?? 'Connecting to intelligence service…'}</p></div>

  const refs = (ids: string[]) => <div className="evidence-links">{ids.map((id) => {
    const evidence = data.evidence[id]
    return evidence ? <button key={id} title={evidence.path} onClick={() => setSelectedEvidence(evidence)}>{evidenceLabel(evidence)}</button> : null
  })}</div>
  const interpretations = (items: Interpretation[], label: string) => items.map((item, index) => <div className="interpretation" key={`${label}-${index}`}><span className="chip">{label}</span> {item.text}{refs(item.evidence_ids)}</div>)
  const send = async (text: string) => {
    if (!text.trim() || busy || data.chat_busy) return
    setBusy('chat')
    const ok = await run('/chat', { message: text.trim() })
    setBusy(null)
    if (ok) { setInput(''); setTab('Ask') }
  }
  const decide = async (id: string, decision: string) => {
    setBusy(id)
    await run(`/proposals/${id}/${decision}`, { run_id: data.run_id })
    setBusy(null)
  }
  return <div className="panel-fill intelligence">
    <div className="intelligence-heading"><div><span className="eyebrow">Powered by Nemotron</span><h2>AVON Intelligence</h2><span className={`agent-status ${data.enabled ? 'online' : ''}`}>{data.status}</span></div>
      <label className="toggle"><input type="checkbox" checked={data.enabled} onChange={(e) => run('/enabled', { enabled: e.target.checked })} />Enabled</label></div>
    <p className="hint">{data.provider} · {data.last_observation_min == null ? 'Waiting for observation' : `observed T+${data.last_observation_min}`}</p>
    {data.provider === 'Deterministic fallback' && <p className="agent-notice">Nemotron offline · Shift handoff and what-if simulations are available.</p>}
    {(error || data.error || data.provider_error || data.audit_error) && <p role="alert" className="agent-notice warn">{error || data.error || data.provider_error || data.audit_error}</p>}
    <nav className="intelligence-tabs" aria-label="Intelligence views">{['Agents', 'Brief', 'Incidents', 'What-if', 'Ask', 'Proposals', 'History'].map(name => <button key={name} aria-pressed={tab === name} className={tab === name ? 'on' : ''} onClick={() => setTab(name)}>{name}</button>)}</nav>
    <div key={tab} className="intel-body">
    {tab === 'Agents' && <AgentTeam data={data} inspect={id => setSelectedEvidence(data.evidence[id] ?? null)} ask={() => setTab('Ask')}/>}
    {tab === 'Brief' && <ShiftDesk data={data} openIncidents={() => setTab('Incidents')} openLab={() => setTab('What-if')} />}
    {tab === 'What-if' && <WhatIfLab data={data} run={run} openEvidence={id => setSelectedEvidence(data.evidence[id] ?? null)} />}

    {tab === 'Incidents' && <>
      {!data.incidents.length && <div className="agent-empty">Watching the network.<p className="hint">Meaningful equipment, alarm, and forecast changes will appear here automatically.</p></div>}
      {data.incidents.map((incident) => <article key={incident.id} className={`incident st-${incident.severity} ${incident.status === 'resolved' ? 'resolved' : ''}`}>
        <div className="opt-top"><span className="chip">{incident.severity.toUpperCase()}</span><span className="hint">{incident.status} · T+{incident.t_min}</span></div>
        <h4>{incident.title}</h4><p>{incident.summary}</p>
        <button className="link-inline" onClick={() => onFocus(incident.affected_assets)}>Highlight affected assets ↗</button>
        <p className="hint">{incident.affected_assets.join(' · ')}</p>
        {incident.automatic.length > 0 && <div className="auto-response"><span className="tag tag-AUTO">AUTO</span>{incident.automatic.map((event) => <p key={event.id}>{event.text}</p>)}</div>}
        <p><span className="tag tag-ADVISORY">ADVISORY</span> {incident.attention}</p>
        <details><summary>Simulator evidence · {incident.evidence_ids.length} readings</summary>{refs(incident.evidence_ids)}</details>
        {interpretations(incident.interpretations, 'Hypothesis')}
        <details><summary>Recommendation critic</summary>{interpretations(incident.concerns, 'Review')}</details>
        {incident.question && <p className="agent-notice">{incident.question}</p>}
        {incident.post_incident_summary && <p>{incident.post_incident_summary}</p>}
      </article>)}
      {data.hypotheses.map((h) => <article className="incident" key={h.id}><h4>Hypothesis: {h.fault.target} · {h.fault.type}</h4><p>{h.meaning}</p>{refs(h.evidence_ids)}</article>)}
    </>}

    {tab === 'Proposals' && <>
      <p className="hint">Alternatives proposed during an investigation appear here. The Decision Engine validates them and checks conditions again at approval.</p>
      {!data.proposals.length && <div className="agent-empty">No investigation proposals. Ranked actions are in the Decision Engine.</div>}
      {[...data.proposals].reverse().map((proposal) => <article className="incident" key={proposal.id}>
        <div className="opt-top"><span className={`tag tag-${proposal.status === 'APPROVED' || proposal.status === 'EXECUTED_IN_SIM' ? 'OPERATOR' : 'ADVISORY'}`}>{proposal.status === 'APPROVED' || proposal.status === 'EXECUTED_IN_SIM' ? 'OPERATOR' : 'ADVISORY'}</span><span className="chip">{proposal.status.replaceAll('_', ' ')}</span></div>
        <h4>{proposal.option?.label ?? proposal.actions.map((a) => `${a.kind} ${a.target}`).join(' + ')}</h4>
        <p className="hint">{proposal.origin === 'NEMOTRON' ? 'Nemotron proposal' : 'Decision engine fallback'} · validated at T+{proposal.t_min}</p>
        {proposal.option && <><div className="agent-metrics"><span><small>Simulated cost</small>{money(proposal.option.cost_breakdown.total)}</span><span><small>HH margin</small>{proposal.option.margin_bbl ?? '—'} bbl</span><span><small>Lead time</small>{proposal.option.lead_time_min} min</span></div><p className="hint">Act by {proposal.option.act_by_clock ?? 'no predicted deadline'} · fixed {money(proposal.option.cost_breakdown.fixed)} · production loss {money(proposal.option.cost_breakdown.production_loss)}</p></>}
        {proposal.reasons.map((reason, index) => <p className="reason" key={index}>{reason}</p>)}
        {refs(proposal.evidence_ids)}
        {proposal.status === 'VALIDATED' && <div className="agent-actions"><button className="primary" disabled={!!busy || !data.enabled} onClick={() => decide(proposal.id, 'approve')}>{busy === proposal.id ? 'Validating…' : 'Approve in simulation'}</button><button disabled={!!busy} onClick={() => decide(proposal.id, 'reject')}>Reject</button></div>}
        {proposal.status === 'EXECUTED_IN_SIM' && <p className="hint">The simulator applied the scheduled effects. Equipment startup, ramping, or transport may still be in progress.</p>}
      </article>)}
    </>}

    {tab === 'Ask' && <>
      {(data.chat_busy || busy === 'chat') && <div className="ask-progress" role="status">Reviewing the plant readings…<div role="progressbar" aria-label="Preparing operator assessment"><i /></div></div>}
      <div className="suggested-questions">{['Why is T-104 filling up?', 'What happens if P-204 becomes unavailable?', 'What changed this shift?'].map((text) => <button key={text} disabled={data.chat_busy || !!busy || !data.enabled} onClick={() => send(text)}>{text}</button>)}</div>
      {data.messages.map((message) => <article className={`agent-message ${message.role}`} key={message.id}><span className={`tag tag-${message.role === 'operator' ? 'OPERATOR' : 'ADVISORY'}`}>{message.role === 'operator' ? 'OPERATOR' : 'ADVISORY'}</span><span className="hint"> T+{message.t_min} {message.source === 'DETERMINISTIC' ? '· Rule-based assessment' : message.source === 'NEMOTRON' ? '· Nemotron' : ''}</span><p>{message.text}</p>{interpretations(message.interpretations ?? [], message.source === 'NEMOTRON' ? 'Nemotron’s read' : 'Operator assessment')}{interpretations(message.concerns ?? [], 'Review')}{message.evidence_ids.some(id => ![...(message.interpretations ?? []), ...(message.concerns ?? [])].some(item => item.evidence_ids.includes(id))) && <details><summary>Supporting readings</summary>{refs(message.evidence_ids.filter(id => ![...(message.interpretations ?? []), ...(message.concerns ?? [])].some(item => item.evidence_ids.includes(id))))}</details>}{message.question && <p className="agent-notice">{message.question}</p>}</article>)}

      <form className="agent-chat" onSubmit={(e) => { e.preventDefault(); void send(input) }}><label htmlFor="agent-question">Ask about the network or a simulated scenario</label><textarea id="agent-question" maxLength={2000} rows={3} value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask AVON Intelligence…" /><button className="primary" disabled={!input.trim() || data.chat_busy || !!busy || !data.enabled}>Analyze</button></form>
      {[...data.scenarios].reverse().map(s => <details key={s.id}><summary>What-if at T+{s.t_min} · {s.faults.map(f => f.target).join(', ')}</summary><ScenarioCompare scenario={s}/>{refs(s.evidence_ids)}</details>)}
    </>}

    {tab === 'History' && <details><summary>Intelligence activity</summary>{[...data.activity].reverse().map((item) => <div className="agent-activity" key={item.id}><span className="hint">T+{item.t_min}</span><div><b>{item.title}</b><p className="hint">{item.detail}</p></div></div>)}<details><summary>Model configuration</summary><p className="hint">Routine: {data.model}<br />Reasoning: {data.reasoning_model}</p></details></details>}

    {tab === 'History' && <>
      <p className="hint">Synthetic maintenance notes and fault observations retain source provenance. They do not change simulation reliability parameters.</p>
      {historyError && <p role="alert">{historyError}</p>}
      <details><summary>Add a maintenance note</summary><form className="agent-chat" onSubmit={async (e) => { e.preventDefault(); setBusy('note'); const ok = await run('/notes', { asset_id: asset, text: note }); if (ok) { setNote(''); setNotesSaved(n => n+1) } setBusy(null) }}><label htmlFor="note-asset">Asset</label><select id="note-asset" value={asset} onChange={(e) => setAsset(e.target.value)}>{assets.map((a) => <option key={a}>{a}</option>)}</select><label htmlFor="maintenance-note">Maintenance observation</label><textarea id="maintenance-note" rows={3} maxLength={4000} value={note} onChange={(e) => setNote(e.target.value)} /><button disabled={!note.trim() || !!busy}>Save simulated note</button></form></details>
      {history && !history.signals.length && <p className="hint">No pump fault events in retained history.</p>}
      {history?.signals.map((signal) => <article className="incident" key={signal.asset_id}><h4>{signal.asset_id} · {signal.observed_fault_events} observed fault events</h4><p className="hint">{signal.interpretation}</p><details><summary>Source events</summary><SourceTimeline rows={signal.sources}/></details></article>)}
      {history?.notes.map((item) => <article className="incident" key={item.id}><h4>{item.data.asset_id}</h4><p>{item.data.text}</p><details><summary>Provenance</summary><p className="hint">{item.data.provenance}<br />{item.at}<br />Run {item.run_id}<br />Record {item.id}</p></details></article>)}<p className="hint">{history?.coverage}</p>
    </>}

    </div>
    {selectedEvidence && <EvidenceViewer evidence={selectedEvidence} readings={data.evidence} inspect={setSelectedEvidence} close={() => setSelectedEvidence(null)} />}
  </div>
}
