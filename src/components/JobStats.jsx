import { formatBytes, formatDuration } from '../lib/format'
import { useCompteurAnime } from '../hooks/useCompteurAnime'

const STATUTS = {
  idle: { texte: 'En attente', point: 'bg-ink-faint', couleur: 'text-ink-soft' },
  checking: { texte: 'Vérification', point: 'bg-busy anim-halo', couleur: 'text-busy' },
  running: { texte: 'Capture en cours', point: 'bg-busy anim-halo', couleur: 'text-busy' },
  done: { texte: 'Terminé', point: 'bg-ok', couleur: 'text-ok' },
  aborted: { texte: 'Interrompu', point: 'bg-warn', couleur: 'text-warn' },
  error: { texte: 'Échec', point: 'bg-err', couleur: 'text-err' },
}

function Ligne({ label, children }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="font-mono text-sm font-medium tabular-nums text-ink">{children}</dd>
    </div>
  )
}

export function JobStats({ job, pagesMax }) {
  const statut = STATUTS[job.status] ?? STATUTS.idle
  const demarre = job.status !== 'idle'
  const enCours = job.status === 'running'

  const pages = useCompteurAnime(job.pages)
  const assets = useCompteurAnime(job.assets)

  const cible = Number(pagesMax) || 1
  // Un site peut compter moins de pages que le budget demandé : une fois le
  // job terminé, la barre est pleine, pas bloquée à 19 %.
  const termine = job.status === 'done'
  const progression = termine ? 100 : Math.min(100, (job.pages / cible) * 100)
  const teinte =
    { done: 'bg-ok', aborted: 'bg-warn', error: 'bg-err' }[job.status] ?? 'bg-accent'

  return (
    <div className="flex flex-col gap-3">
      <div className="h-1.5 overflow-hidden rounded-full bg-line">
        <div
          className={`h-full rounded-full transition-all duration-500 ease-out ${teinte} ${
            enCours ? 'bande-active' : ''
          }`}
          style={{ width: demarre ? `${Math.max(progression, 3)}%` : '0%' }}
          role="progressbar"
          aria-valuenow={job.pages}
          aria-valuemin={0}
          aria-valuemax={cible}
        />
      </div>

      <dl className="divide-y divide-line">
        <Ligne label="Statut">
          <span className={`flex items-center gap-2 font-sans text-sm ${statut.couleur}`}>
            <span className={`inline-block size-2 rounded-full ${statut.point}`} />
            {statut.texte}
          </span>
        </Ligne>
        <Ligne label="Durée">{demarre ? formatDuration(job.duration) : '—'}</Ligne>
        <Ligne label="Pages">{demarre ? pages : '—'}</Ligne>
        <Ligne label="Ressources">{demarre ? assets : '—'}</Ligne>
        <Ligne label="Poids">{demarre ? formatBytes(job.bytes) : '—'}</Ligne>
      </dl>
    </div>
  )
}
