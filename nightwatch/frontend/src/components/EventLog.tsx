import { useEffect, useRef, useState } from 'react'
import type { SimEvent } from '../types'

const TAGS = ['AUTO', 'ADVISORY', 'OPERATOR', 'FAULT', 'ALARM', 'SYSTEM']

export function EventLog({ events }: { events: SimEvent[] }) {
  const [on, setOn] = useState<Set<string>>(new Set(TAGS))
  const end = useRef<HTMLDivElement>(null)
  const shown = events.filter((e) => on.has(e.tag))
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest' }) }, [shown.length])
  const toggle = (t: string) => setOn((p) => { const n = new Set(p); if (n.has(t)) n.delete(t); else n.add(t); return n })
  return (
    <div className="panel-fill scroll">
      <div className="panel-head">
        <h3>Event log</h3>
        <div className="seg">{TAGS.map((t) => <button key={t} className={on.has(t) ? `on tag-${t}` : ''} onClick={() => toggle(t)}>{t}</button>)}</div>
      </div>
      {shown.map((e) => (
        <div key={e.id} className="event">
          <span className="t">T+{e.t_min}</span>
          <span className={`tag tag-${e.tag}`}>{e.tag}</span>
          <span>{e.text}</span>
        </div>
      ))}
      <div ref={end} />
    </div>
  )
}
