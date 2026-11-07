import { useState } from 'react'
import type { SimEvent } from '../types'
import { eventText } from '../format'

const TAGS = ['AUTO', 'ADVISORY', 'OPERATOR', 'FAULT', 'ALARM', 'SYSTEM']

export function EventLog({ events }: { events: SimEvent[] }) {
  const [on, setOn] = useState<Set<string>>(new Set(TAGS))

  const shown = events.filter((e) => on.has(e.tag))

  const toggle = (t: string) => setOn((p) => { const n = new Set(p); if (n.has(t)) n.delete(t); else n.add(t); return n })
  return (
    <div className="panel-fill scroll">
      <div className="panel-head">
        <h3>Event log</h3>
        <div className="event-filters">{TAGS.map((t) => <button key={t} aria-pressed={on.has(t)} className={on.has(t) ? `on tag-${t}` : ''} onClick={() => toggle(t)}>{t}</button>)}</div>
      </div>
      {shown.length === 0 && <p className="hint">No matching events in this run.</p>}
      {[...shown].reverse().map((e) => (
        <div key={e.id} className="event">
          <span className="t">T+{e.t_min}</span>
          <span className={`tag tag-${e.tag}`}>{e.tag}</span>
          <span>{eventText(e.text)}</span>
        </div>
      ))}

    </div>
  )
}
