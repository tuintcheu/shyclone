import { useEffect, useState } from 'react'
import { Clock, Trash2 } from 'lucide-react'

function restantDepuis(expiresAt) {
  if (!expiresAt) return null
  return Math.max(0, Math.round((expiresAt - Date.now()) / 1000))
}

function mmss(secondes) {
  const m = Math.floor(secondes / 60)
  const s = secondes % 60
  return `${m}:${String(s).padStart(2, '0')}`
}

/**
 * Annonce la durée de conservation d'une capture, puis décompte une fois le
 * clonage terminé. Le moteur supprime les fichiers à l'échéance : l'utilisateur
 * doit le savoir avant de compter dessus.
 */
export function RetentionNotice({ expiresAt, retentionMinutes, onExpire }) {
  const [restant, setRestant] = useState(() => restantDepuis(expiresAt))

  // Monté avec `key={expiresAt}` côté App : l'état initial est déjà correct,
  // l'effet n'a qu'à entretenir le décompte.
  useEffect(() => {
    if (!expiresAt) return undefined

    const id = setInterval(() => {
      const valeur = restantDepuis(expiresAt)
      setRestant(valeur)
      if (valeur === 0) {
        clearInterval(id)
        onExpire?.()
      }
    }, 1000)
    return () => clearInterval(id)
  }, [expiresAt, onExpire])

  if (restant === null) {
    return (
      <p className="flex items-start gap-2 text-xs leading-relaxed text-ink-faint">
        <Clock size={13} className="mt-px shrink-0" />
        <span>
          Les captures sont conservées {retentionMinutes} minutes après la fin du
          clonage, puis supprimées automatiquement. Téléchargez l'archive pour
          les garder.
        </span>
      </p>
    )
  }

  if (restant === 0) {
    return (
      <p className="anim-apparition flex items-start gap-2 rounded-lg border border-warn/40 bg-warn/10 px-3 py-2.5 text-xs leading-relaxed text-warn">
        <Trash2 size={13} className="mt-px shrink-0" />
        <span>
          Capture expirée : les fichiers ont été supprimés du serveur. Relancez
          le clonage pour la consulter à nouveau.
        </span>
      </p>
    )
  }

  const urgent = restant <= 120
  return (
    <p
      className={`flex items-start gap-2 rounded-lg border px-3 py-2.5 text-xs leading-relaxed ${
        urgent ? 'border-warn/40 bg-warn/10 text-warn' : 'border-line bg-raised text-ink-soft'
      }`}
    >
      <Clock size={13} className={`mt-px shrink-0 ${urgent ? 'anim-battement' : ''}`} />
      <span>
        Suppression automatique dans{' '}
        <span className="font-mono font-semibold tabular-nums">{mmss(restant)}</span>.
        Téléchargez l'archive pour conserver cette capture.
      </span>
    </p>
  )
}
