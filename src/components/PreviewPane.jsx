import { useState } from 'react'
import { Download, ExternalLink, Laptop, RotateCw, Smartphone, Tablet } from 'lucide-react'
import { BuildingPreview } from './BuildingPreview'
import { Mark } from './Logo'

const FORMATS = [
  { id: 'desktop', label: 'Bureau', icone: Laptop, largeur: '100%' },
  { id: 'tablet', label: 'Tablette', icone: Tablet, largeur: '820px' },
  { id: 'mobile', label: 'Mobile', icone: Smartphone, largeur: '390px' },
]

/* Monté avec `key={src}` : chaque nouvelle capture repart d'un état non chargé,
   sans effet de synchronisation. */
function Cadre({ src, largeur }) {
  const [charge, setCharge] = useState(false)
  return (
    <iframe
      src={src}
      onLoad={() => setCharge(true)}
      title="Aperçu du site capturé"
      style={{ width: largeur, maxWidth: '100%' }}
      className={`h-full border-none bg-white transition-opacity duration-500 ${
        charge ? 'opacity-100' : 'opacity-0'
      }`}
      /* allow-same-origin est nécessaire pour que les scripts du site capturé
         puissent lire localStorage : sans lui, le sélecteur de thème ou le
         choix de langue d'un site cloné lèvent une exception et cassent. Le
         risque est contenu parce que l'aperçu est servi depuis l'origine du
         moteur, distincte de celle de ShyClone (voir lib/api.js). */
      sandbox="allow-scripts allow-popups allow-forms allow-same-origin"
    />
  )
}

export function PreviewPane({
  src,
  host,
  viewport,
  onViewportChange,
  zipHref,
  version,
  job,
  pageCourante,
}) {
  const format = FORMATS.find(f => f.id === viewport) ?? FORMATS[0]
  const [rechargements, setRechargements] = useState(0)
  const enConstruction = job.status === 'checking' || job.status === 'running'

  return (
    <section className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-sm font-semibold text-ink">Aperçu de la capture</h2>

        <div className="flex items-center gap-2">
          <div className="flex items-center gap-0.5 rounded-lg border border-line bg-raised p-1">
            {FORMATS.map(({ id, label, icone: Icone }) => (
              <button
                key={id}
                type="button"
                onClick={() => onViewportChange(id)}
                aria-pressed={viewport === id}
                className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-medium transition-all duration-200 ${
                  viewport === id
                    ? 'bg-invert-bg text-invert-ink shadow-sm'
                    : 'text-ink-soft hover:bg-surface hover:text-ink'
                }`}
              >
                <Icone size={13} />
                <span className="hidden sm:inline">{label}</span>
              </button>
            ))}
          </div>

          {zipHref && (
            <a
              href={zipHref}
              download
              className="anim-apparition flex items-center gap-1.5 rounded-lg border border-line bg-raised px-3 py-2 text-xs font-medium text-ink-soft transition-all duration-200 hover:border-line-strong hover:text-ink active:scale-95"
            >
              <Download size={13} />
              Archive .zip
            </a>
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-line bg-surface shadow-sm">
        <div className="flex shrink-0 items-center gap-3 border-b border-line px-3.5 py-2.5">
          <span className="truncate font-mono text-xs text-ink-faint">
            {enConstruction
              ? `${host || 'site'} — construction…`
              : src
                ? host || 'capture locale'
                : 'aucune capture'}
          </span>
          {src && !enConstruction && (
            <button
              type="button"
              onClick={() => setRechargements(v => v + 1)}
              title="Recharger l'aperçu"
              className="ml-auto flex shrink-0 items-center gap-1.5 text-xs font-medium text-ink-soft transition-colors hover:text-ink"
            >
              <RotateCw size={12} />
              Recharger
            </button>
          )}
          {src && !enConstruction && (
            <a
              href={src}
              target="_blank"
              rel="noreferrer"
              className="flex shrink-0 items-center gap-1.5 text-xs font-medium text-ink-soft transition-colors hover:text-ink"
            >
              <ExternalLink size={12} />
              Nouvel onglet
            </a>
          )}
        </div>

        <div className="flex min-h-0 flex-1 justify-center overflow-auto bg-canvas">
          {enConstruction ? (
            <BuildingPreview job={job} pageCourante={pageCourante} />
          ) : src ? (
            <Cadre key={`${src}|${version}|${rechargements}`} src={src} largeur={format.largeur} />
          ) : (
            <div className="anim-apparition flex flex-col items-center justify-center gap-4 px-6 text-center">
              <Mark className="h-16 opacity-25" />
              <p className="text-sm font-medium text-ink-soft">Aucune capture à afficher</p>
              <p className="max-w-xs text-xs leading-relaxed text-ink-faint">
                Lancez une capture : les pages téléchargées s'afficheront ici, servies
                depuis votre disque et non depuis le site d'origine.
              </p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
