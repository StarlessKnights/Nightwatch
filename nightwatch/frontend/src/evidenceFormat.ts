import type { Evidence } from './agentTypes'

export const sourceNames: Record<string,string> = { get_forecast: 'Hall thermal forecast', get_asset_state: 'Equipment readings', get_impact: 'Connected assets', get_recommendations: 'Decision Engine', get_event_history: 'Recorded event', submit_scenario_proposal: 'What-if lab', get_active_alarms: 'Alarm journal', submit_action_proposal: 'Action validation', get_shift_brief: 'Shift handoff' }
export function evidenceLabel(e: Evidence) {
  if (e.label !== e.path) return e.label
  if (e.path.startsWith('impact.')) return e.path.slice(7) + ' · connections'
  if (e.path.startsWith('forecast.')) return e.path.slice(9) + ' · forecast'
  return sourceNames[e.source] ?? e.label.replaceAll('_', ' ')
}
