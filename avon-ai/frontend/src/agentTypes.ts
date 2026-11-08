import type { Option, SimEvent } from './types'

export interface Trend { tank: string; change_bbl: number; samples: { t: number; bbl: number }[] }
export interface ShiftBrief {
  run_id: string; t_min: number; from_min: number; trends: Trend[]; recent_events: SimEvent[]
  unacknowledged: number; forecast_as_of: number; horizon_min: number
  first_limit: { tank: string; at_min: number } | null
}
export interface SourceRecord {
  id: string; at: string; run_id: string; data: SimEvent
}

export interface Evidence {
  id: string; run_id: string; revision: number; t_min: number
  source: string; path: string; label: string; value: unknown
}
export interface Interpretation { text: string; evidence_ids: string[] }
export interface TeamReport {
  focus_asset_ids: string[]
  tool_events: { tool: string; status: string; evidence_ids: string[]; origin?: string }[]
  started_at: number | null; completed_at: number | null
  role: string; model: string; observation: string; evidence_ids: string[]
  status: string; source: string | null; interpretations: Interpretation[]; error: string | null
}
export interface Investigation {
  id: string; run_id: string; revision: number; t_min: number; trigger: string
  reports: TeamReport[]
  events: { role: string; status: string; elapsed_s: number; source: string | null }[]
}
export interface Incident {
  id: string; title: string; status: string; severity: string; t_min: number; first_seen_min: number
  affected_assets: string[]; roots: string[]; evidence_ids: string[]; summary: string; attention: string
  source: string; automatic: { id: number; text: string }[]
  interpretations: Interpretation[]; concerns: Interpretation[]; question: string | null
  post_incident_summary?: string
}
export interface Proposal {
  id: string; run_id: string; t_min: number; status: 'PENDING' | 'VALIDATED' | 'REJECTED' | 'APPROVED' | 'EXECUTED_IN_SIM'
  actions: { kind: string; target: string; pct: number | null }[]
  evidence_ids: string[]; reasons: string[]; option: Option | null; origin: string
  outcomes?: Record<string, { text: string }>
}
export interface AgentMessage {
  id: string; role: 'operator' | 'agent'; text: string; t_min: number; source?: string
  evidence_ids: string[]; interpretations?: Interpretation[]; concerns?: Interpretation[]; question?: string | null
}
export interface ScenarioResult {
  horizon_min: number
  baseline: { do_nothing_cost: number; forecast: ScenarioResult['forecast'] }
  id: string; t_min: number; evidence_ids: string[]; best_option_id: string | null; do_nothing_cost: number
  faults: { type: string; target: string; params: Record<string, unknown> }[]
  forecast: Record<string, { time_to_HH: number | null; status: string }>
}
export interface AgentState {
  team: Investigation | null
  shift_brief: ShiftBrief | null
  run_id: string; enabled: boolean; status: string; provider: string; model: string; reasoning_model: string
  provider_error: string | null; error: string | null; audit_error: string | null; last_observation_min: number | null
  incidents: Incident[]; proposals: Proposal[]; messages: AgentMessage[]; scenarios: ScenarioResult[]
  hypotheses: { id: string; fault: { type: string; target: string }; meaning: string; evidence_ids: string[] }[]
  activity: { id: string; t_min: number; title: string; detail: string }[]
  evidence: Record<string, Evidence>; chat_busy: boolean
}
