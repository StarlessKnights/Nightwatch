import { useEffect, useRef, type ReactNode } from 'react'

export function OperatorDialog({ title, close, children }: { title: string; close: () => void; children: ReactNode }) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const el = ref.current!
    el.showModal()
    return () => el.close()
  }, [])
  return <dialog ref={ref} className="operator-dialog" aria-label={title} onCancel={close}
    onClick={e => { if (e.target === ref.current) close() }}>
    <section><header><h2>{title}</h2><button autoFocus onClick={close}>Close</button></header>{children}</section>
  </dialog>
}
