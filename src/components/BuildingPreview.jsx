import { Loader2 } from 'lucide-react'

/* Maquette de page dont les blocs apparaissent l'un après l'autre.
   Elle est remontée à chaque nouvelle page écrite par le moteur (`key` sur le
   compteur côté parent) : la séquence rejoue donc au rythme réel de la
   capture, elle n'est pas une boucle décorative indépendante. */
function Maquette() {
  let rang = 0
  const bloc = (className, contenu = null) => {
    const delai = { animationDelay: `${rang++ * 85}ms` }
    return (
      <div className={`bloc-construit ${className}`} style={delai}>
        {contenu}
      </div>
    )
  }

  return (
    <div className="flex w-full max-w-lg flex-col gap-4 p-6">
      {/* barre de navigation */}
      {bloc(
        'flex items-center gap-3 rounded-md border border-line bg-surface px-3 py-2.5',
        <>
          <span className="squelette size-4 rounded" />
          <span className="flex-1" />
          <span className="squelette h-2 w-10 rounded-full" />
          <span className="squelette h-2 w-10 rounded-full" />
          <span className="squelette h-2 w-10 rounded-full" />
        </>,
      )}

      {/* titre et paragraphe */}
      <div className="flex flex-col gap-2.5 pt-2">
        {bloc('squelette h-5 w-3/5 rounded')}
        {bloc('squelette h-2.5 w-11/12 rounded-full')}
        {bloc('squelette h-2.5 w-4/6 rounded-full')}
      </div>

      {bloc('squelette h-8 w-32 rounded-md')}

      {/* rangée d'illustrations */}
      <div className="grid grid-cols-3 gap-3 pt-2">
        {bloc('squelette h-20 rounded-md')}
        {bloc('squelette h-20 rounded-md')}
        {bloc('squelette h-20 rounded-md')}
      </div>

      <div className="flex flex-col gap-2.5 pt-1">
        {bloc('squelette h-2.5 w-10/12 rounded-full')}
        {bloc('squelette h-2.5 w-7/12 rounded-full')}
      </div>

      {bloc('squelette mt-2 h-10 rounded-md')}
    </div>
  )
}

export function BuildingPreview({ job, pageCourante }) {
  const verification = job.status === 'checking'

  return (
    <div className="relative flex h-full w-full items-start justify-center overflow-hidden">
      {/* balayage lumineux, purement visuel */}
      <div
        aria-hidden="true"
        className="balayage pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-transparent via-accent/10 to-transparent"
      />

      {/* La clé force le remontage à chaque page : la maquette se reconstruit. */}
      <Maquette key={job.pages} />

      <div className="pointer-events-none absolute inset-x-0 bottom-0 flex flex-col items-center gap-1.5 bg-gradient-to-t from-canvas via-canvas to-transparent px-6 pb-5 pt-10">
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Loader2 size={14} className="animate-spin text-accent" />
          {verification ? 'Vérification du site…' : `Page ${job.pages + 1} en cours`}
        </p>
        <p className="max-w-full truncate font-mono text-xs text-ink-faint">
          {pageCourante || 'analyse des liens…'}
        </p>
      </div>
    </div>
  )
}
