import { useId } from 'react'
import { Loader2, Play, Square } from 'lucide-react'
import { isValidUrl, normalizeUrl } from '../lib/url'

export const PAGES_MAX = 5000
const RACCOURCIS = [25, 100, 500, PAGES_MAX]

export function CloneForm({
  url,
  onUrlChange,
  pagesMax,
  onPagesMaxChange,
  status,
  engineDown,
  onSubmit,
  onAbort,
}) {
  const idUrl = useId()
  const idPages = useId()

  const enCours = status === 'running'
  const verifie = status === 'checking'
  const valide = isValidUrl(normalizeUrl(url))

  const soumettre = event => {
    event.preventDefault()
    if (!enCours && !verifie && valide) onSubmit()
  }

  return (
    <form onSubmit={soumettre} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <label htmlFor={idUrl} className="text-xs font-semibold text-ink-soft">
          Adresse du site
        </label>
        <input
          id={idUrl}
          type="text"
          inputMode="url"
          value={url}
          onChange={e => onUrlChange(e.target.value)}
          onBlur={() => url.trim() && onUrlChange(normalizeUrl(url))}
          placeholder="exemple.com"
          disabled={enCours || verifie}
          autoComplete="off"
          spellCheck={false}
          className="w-full rounded-lg border border-line bg-surface px-3 py-2.5 font-mono text-sm text-ink transition-colors duration-200 placeholder:text-ink-faint hover:border-line-strong focus:border-focus disabled:opacity-55"
        />
        <p className="min-h-4 text-xs text-ink-faint">
          {url.trim() && !/^https?:\/\//i.test(url.trim())
            ? 'https:// sera ajouté automatiquement.'
            : ''}
        </p>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor={idPages} className="text-xs font-semibold text-ink-soft">
            Pages maximum
          </label>
          <input
            id={idPages}
            type="number"
            min={1}
            max={PAGES_MAX}
            value={pagesMax}
            onChange={e => onPagesMaxChange(e.target.value)}
            disabled={enCours || verifie}
            className="w-24 rounded-lg border border-line bg-surface px-2.5 py-1.5 text-right font-mono text-sm font-medium tabular-nums text-ink transition-colors duration-200 hover:border-line-strong focus:border-focus disabled:opacity-55"
          />
        </div>

        <div className="grid grid-cols-4 gap-1 rounded-lg border border-line bg-raised p-1">
          {RACCOURCIS.map(valeur => {
            const actif = Number(pagesMax) === valeur
            return (
              <button
                key={valeur}
                type="button"
                onClick={() => onPagesMaxChange(String(valeur))}
                disabled={enCours || verifie}
                aria-pressed={actif}
                className={`rounded-md py-1.5 font-mono text-xs font-medium tabular-nums transition-all duration-200 ${
                  actif
                    ? 'bg-invert-bg text-invert-ink shadow-sm'
                    : 'text-ink-soft hover:bg-surface hover:text-ink disabled:opacity-45'
                }`}
              >
                {valeur === PAGES_MAX ? 'Max' : valeur}
              </button>
            )
          })}
        </div>
      </div>

      {enCours ? (
        <button
          type="button"
          onClick={onAbort}
          className="flex items-center justify-center gap-2 rounded-lg border border-err/45 bg-err/12 px-4 py-3 text-sm font-semibold text-err transition-all duration-200 hover:bg-err/20 active:scale-[0.98]"
        >
          <Square size={13} fill="currentColor" />
          Interrompre
        </button>
      ) : (
        <button
          type="submit"
          disabled={!valide || verifie || engineDown}
          className="flex items-center justify-center gap-2 rounded-lg border border-transparent bg-invert-bg px-4 py-3 text-sm font-semibold text-invert-ink shadow-sm transition-all duration-200 hover:shadow-md active:scale-[0.98] disabled:cursor-not-allowed disabled:border-line disabled:bg-transparent disabled:text-ink-faint disabled:shadow-none"
        >
          {verifie ? (
            <>
              <Loader2 size={15} className="animate-spin" />
              Vérification…
            </>
          ) : (
            <>
              <Play size={14} fill="currentColor" />
              Lancer la capture
            </>
          )}
        </button>
      )}

      {engineDown && (
        <p className="anim-apparition rounded-lg border border-err/40 bg-err/10 px-3 py-2.5 text-xs leading-relaxed text-err">
          Service momentanément indisponible. La capture sera de nouveau possible
          dès qu'il répond.
        </p>
      )}
    </form>
  )
}
