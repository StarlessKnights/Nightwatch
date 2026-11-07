import { useState } from 'react'
import { api } from '../api'
import type { Envelope } from '../types'
import { OperatorDialog } from './OperatorDialog'

const conditionName = (code: string) => ({ FORECAST_HH: 'Predicted high-high level', HH: 'High-high level', H: 'High level', L: 'Low level', LL: 'Low-low level' }[code] ?? code.toLowerCase().replaceAll('_', ' '))

export function AlarmList({ env, run }: { env: Envelope; run: (fn: () => Promise<unknown>) => Promise<void> }) {
  const [open, setOpen] = useState(false), [cleared, showCleared] = useState(false)
  const active = env.state.alarms.filter(a => a.state !== 'CLEARED').sort((a,b) => a.priority - b.priority || Number(b.state === 'ACTIVE_UNACK') - Number(a.state === 'ACTIVE_UNACK') || b.raised_min - a.raised_min)
  const past = env.state.alarms.filter(a => a.state === 'CLEARED').sort((a,b) => (b.cleared_min ?? 0) - (a.cleared_min ?? 0))
  const top = active[0], unack = active.filter(a => a.state === 'ACTIVE_UNACK').length
  return <><button className={'alarm-shelf ' + (top ? 'p' + top.priority : '')} onClick={() => { showCleared(false); setOpen(true) }} aria-haspopup="dialog">
    <b>{top ? active.length + (active.length === 1 ? ' active alarm' : ' active alarms') : 'Alarms clear'}</b><span>{top ? 'P' + top.priority + ' · ' + top.tag + ' · ' + conditionName(top.condition) : 'No active alarms'}</span><strong>{unack ? unack + ' to acknowledge · ' : ''}View ›</strong></button>
    {open && <OperatorDialog title="Alarm desk" close={() => setOpen(false)}><div className="desk-tabs"><button aria-pressed={!cleared} onClick={() => showCleared(false)}>Active ({active.length})</button><button aria-pressed={cleared} onClick={() => showCleared(true)}>Cleared ({past.length})</button></div>
      {!(cleared ? past : active).length && <p className="agent-empty">No {cleared ? 'cleared' : 'active'} alarms.</p>}
      {(cleared ? past : active).map(a => <article className={'alarm p'+a.priority} key={a.id}><b>P{a.priority}</b><div className="grow"><strong>{a.tag}</strong> · {conditionName(a.condition)}<p className="hint">{a.kind === 'PREDICTIVE' ? 'Forecast · ' : ''}Raised T+{a.raised_min} · {a.state === 'ACTIVE_UNACK' ? 'Needs acknowledgment' : a.state === 'ACTIVE_ACK' ? 'Acknowledged' : 'Cleared T+' + a.cleared_min}{a.value != null && ' · Reading ' + a.value.toFixed(1)}</p></div>
        {a.state === 'ACTIVE_UNACK' && <button onClick={() => run(() => api.ack(a.id))}>Acknowledge</button>}</article>)}
    </OperatorDialog>}</>
}
