export type Json = Record<string, any>

export interface TankForecast {
  tank: string
  time_to_H: number | null
  time_to_HH: number | null
  time_to_overflow: number | null
  confidence: string
  status: 'normal' | 'watch' | 'warning' | 'critical'
  series: number[]
}

export interface Alarm {
  id: string; tag: string; condition: string; priority: number; kind: string
  state: 'ACTIVE_UNACK' | 'ACTIVE_ACK' | 'CLEARED'
  raised_min: number; cleared_min: number | null; value: number | null; text: string
}

export interface SimEvent {
  id: number; t_min: number; tag: string; code: string; asset: string | null; params: Json; text: string
}

export interface SimStateDto {
  run_id: string
  revision: number
  t_min: number
  clock: string
  tanks: Record<string, Json>
  pumps: Record<string, Json>
  sources: Record<string, Json>
  pipelines: Record<string, Json>
  treatment: Record<string, Json>
  faults: { id: string; type: string; target: string; params: Json; start_min: number; end_min: number | null; active: boolean }[]
  alarms: Alarm[]
  pending_actions: { id: string; kind: string; effective_at_min: number; label: string }[]
}

export interface Payoff {
  option_id: string; label: string; approved_min: number
  do_nothing_cost: number; action_cost: number; savings: number
}

export interface Envelope {
  running: boolean
  speed: number
  engine_enabled: boolean
  auto_changeover_on_low_flow: boolean
  scenario: { id: string; name: string; description: string }
  state: SimStateDto
  forecast: { tanks: Record<string, TankForecast>; do_nothing: Record<string, number[]> | null; series_step_min: number; as_of_min: number }
  payoff: Payoff | null
  ledger: { loss: number; saved: number; net: number; breakdown: Record<string, number> }
}

export interface HistoryPoint { t: number; [tank: string]: number }

export interface Option {
  action_id: string; label: string; feasible: boolean
  reason_codes: string[]; reasons: { code: string; text: string }[]
  cost_breakdown: { fixed: number; hourly: number; production_loss: number; expected_consequence: number; total: number | null }
  margin_bbl: number | null; act_by_min: number | null; act_by_clock: string | null; lead_time_min: number
  trajectory_summary: Record<string, { peak_bbl: number; final_bbl: number; time_to_HH: number | null; series: number[] }> | null
}

export interface Recommendation {
  as_of_min: number; headline: string; headline_code: string; status: string
  forecast: Record<string, TankForecast>
  probable_cause: { asset: string; evidence_field: string; value: unknown }[]
  affected_assets: { upstream: string[]; downstream: string[]; first_to_limit: string | null }
  options: Option[]; ranked_option_ids: string[]; best_option_id: string | null
  do_nothing_cost: number; savings: number; engine_enabled: boolean
}

export interface Network {
  topology: { nodes: Json[]; edges: { from: string; to: string; kind: string }[] }
  config: Json
  fault_catalog: Record<string, { target_kind: string; handled_by: string; params: Record<string, Json> }>
  scenarios: { id: string; name: string; description: string; decision_engine_enabled: boolean }[]
}

export interface PumpDiagnosis { code: string; w_est: number | null; r_est: number | null; evidence: { field: string; value: number }[]; text?: string }

export interface AssetHistory {
  kind: 'pump' | 'tank'
  series: Record<string, (number | null)[]>
  events: { t: number; kind: string; label: string }[]
  expected_flow: number[]
}

export interface CurvePoint { Q: number; H: number }
export interface Curves {
  pump_curve: CurvePoint[]; pump_curve_healthy: CurvePoint[]
  system_curve: CurvePoint[]; system_curve_healthy: CurvePoint[]
  operating_point: { Q: number; H: number }
  healthy_point: { Q: number; H: number }
  running: boolean; w: number; r: number
}
