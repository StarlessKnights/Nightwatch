export const money = (n: number | null | undefined) =>
  n == null ? '—' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export const num = (n: number | null | undefined, d = 1) => (n == null ? '—' : n.toFixed(d))

export function clock(tMin: number, start = '00:00'): string {
  const [h, m] = start.split(':').map(Number)
  const total = Math.round(h * 60 + m + tMin)
  const mm = ((total % 60) + 60) % 60
  const hh = (Math.floor(total / 60) % 24 + 24) % 24
  return `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}`
}

export const compactNumber = (v: number) => v.toLocaleString(undefined, { maximumFractionDigits: 1 })

const eventTerms: Record<string,string> = {
  PUMP_DEGRADE: 'reduced pump capacity', PUMP_TRIP: 'pump trip', PUMP_UNAVAILABLE: 'pump unavailable',
  TREATMENT_CONSTRAINT: 'reduced treatment capacity', PIPELINE_RESTRICTION: 'pipeline restriction',
  INFLOW_SURGE: 'inflow surge', LEVEL_SENSOR_FAULT: 'level sensor fault', FORECAST_HH: 'predicted high-high level',
}
export const eventText = (text: string) => text.replace(/\b[A-Z]+(?:_[A-Z]+)+\b/g, term => eventTerms[term] ?? term)
