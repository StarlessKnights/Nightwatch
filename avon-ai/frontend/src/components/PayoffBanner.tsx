import { money } from '../format'
import type { Envelope, Recommendation } from '../types'

export function PayoffBanner({ env, rec }: { env: Envelope; rec: Recommendation | null }) {
  const p = env.payoff
  if (p) {
    return (
      <div className="payoff done">
        <b>{money(p.savings)} avoided</b>
        <span>“{p.label}” approved at T+{p.approved_min}: {money(p.action_cost)} vs {money(p.do_nothing_cost)} if nothing had been done.</span>
      </div>
    )
  }
  if (rec && rec.savings > 0) {
    return (
      <div className="payoff">
        <b>{money(rec.savings)} potential savings</b>
        <span>Best option vs do-nothing ({money(rec.do_nothing_cost)}, derived from the do-nothing rollout).</span>
      </div>
    )
  }
  return null
}
