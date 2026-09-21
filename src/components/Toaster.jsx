import { useEffect } from 'react'
import { AlertTriangle, Check, Info, X } from 'lucide-react'

const DUREE = 6000

const TONS = {
  ok: { classe: 'border-ok/35 text-ok', Icone: Check },
  warn: { classe: 'border-warn/35 text-warn', Icone: AlertTriangle },
  error: { classe: 'border-err/35 text-err', Icone: AlertTriangle },
  info: { classe: 'border-line text-ink-soft', Icone: Info },
}

function Toast({ toast, onDismiss }) {
  const { id, message, tone } = toast
  const { classe, Icone } = TONS[tone] ?? TONS.info

  // Le composant est monté avec `key={id}` : chaque notification a donc son
  // propre minuteur, qu'un re-rendu du parent ne réarme pas.
  useEffect(() => {
    const minuteur = setTimeout(() => onDismiss(id), DUREE)
    return () => clearTimeout(minuteur)
  }, [id, onDismiss])

  return (
    <div
      role="status"
      className={`anim-toast flex w-80 max-w-[calc(100vw-2rem)] items-start gap-2.5 rounded-lg border bg-surface px-3.5 py-3 shadow-xl ${classe}`}
    >
      <Icone size={15} className="mt-px shrink-0" />
      <p className="flex-1 text-sm leading-snug text-ink">{message}</p>
      <button
        type="button"
        onClick={() => onDismiss(id)}
        aria-label="Fermer la notification"
        className="shrink-0 text-ink-faint transition-colors hover:text-ink"
      >
        <X size={14} />
      </button>
    </div>
  )
}

export function Toaster({ toasts, onDismiss }) {
  if (toasts.length === 0) return null
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-40 flex flex-col gap-2">
      {toasts.map(toast => (
        <div key={toast.id} className="pointer-events-auto">
          <Toast toast={toast} onDismiss={onDismiss} />
        </div>
      ))}
    </div>
  )
}
