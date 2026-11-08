import { useEffect, useRef, type ReactNode } from 'react'

/** Remains mounted while closed so forms and filters retain their state. */
export function WorkspaceDialog({ open, onClose, title, children }: {
  open: boolean; onClose: () => void; title: string; children: ReactNode
}) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const dialog = ref.current!
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])
  return <dialog ref={ref} className="workspace-dialog" aria-label={title} onCancel={onClose}>
    <header><h2>{title}</h2><button autoFocus onClick={onClose}>Close</button></header>
    <div className="workspace-dialog-body">{children}</div>
  </dialog>
}
