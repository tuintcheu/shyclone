import { useEffect, useRef } from 'react'
import { formatStamp } from '../lib/format'

const NIVEAUX = {
  info: 'bg-ink-faint',
  ok: 'bg-ok',
  warn: 'bg-warn',
  error: 'bg-err',
}

/** Journal des événements réellement émis par le moteur. */
export function ActivityLog({ events }) {
  const conteneurRef = useRef(null)
  const suivreRef = useRef(true)

  useEffect(() => {
    const el = conteneurRef.current
    if (el && suivreRef.current) el.scrollTop = el.scrollHeight
  }, [events])

  // On cesse de suivre dès que l'utilisateur remonte lire une ligne.
  const surDefilement = event => {
    const el = event.currentTarget
    suivreRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 32
  }

  return (
    <div
      ref={conteneurRef}
      onScroll={surDefilement}
      className="h-full min-h-0 overflow-y-auto rounded-lg border border-line bg-raised"
    >
      {events.length === 0 ? (
        <p className="p-3 text-xs text-ink-faint">
          Le journal du moteur s'affichera ici pendant la capture.
        </p>
      ) : (
        <ol className="divide-y divide-line/60">
          {events.map(evenement => (
            <li key={evenement.i} className="anim-laterale flex gap-2.5 px-3 py-2">
              <span
                className={`mt-[7px] size-1.5 shrink-0 rounded-full ${NIVEAUX[evenement.niveau] ?? NIVEAUX.info}`}
              />
              <span className="min-w-0 flex-1 break-words text-xs leading-relaxed text-ink-soft">
                {evenement.texte}
              </span>
              <span className="shrink-0 pt-px font-mono text-[11px] tabular-nums text-ink-faint">
                {formatStamp(evenement.t)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}
