import { useCallback, useMemo, useState } from 'react'
import { ActivityLog } from './components/ActivityLog'
import { CloneForm, PAGES_MAX } from './components/CloneForm'
import { JobStats } from './components/JobStats'
import { PreviewPane } from './components/PreviewPane'
import { RetentionNotice } from './components/RetentionNotice'
import { Toaster } from './components/Toaster'
import { TopBar } from './components/TopBar'
import { UnreachableDialog } from './components/UnreachableDialog'
import { useCloneJob } from './hooks/useCloneJob'
import { useEngineHealth } from './hooks/useEngineHealth'
import { useTheme } from './hooks/useTheme'
import { useToasts } from './hooks/useToasts'
import { previewUrl, zipUrl } from './lib/api'
import { hostOf, normalizeUrl } from './lib/url'

const PAGES_DEFAUT = 50

export default function App() {
  const { theme, toggle } = useTheme()
  const { state: engine, rendu: renduDisponible } = useEngineHealth()
  const { toasts, push, dismiss } = useToasts()

  const [url, setUrl] = useState('')
  const [mode, setMode] = useState('site')
  const [cookies, setCookies] = useState('')
  const [renduJs, setRenduJs] = useState(false)
  const [pagesMax, setPagesMax] = useState(String(PAGES_DEFAUT))
  const [viewport, setViewport] = useState('desktop')
  const [injoignable, setInjoignable] = useState(null)
  const [expire, setExpire] = useState(false)

  const surFin = useCallback(
    (statut, charge) => {
      if (statut === 'done') {
        push(
          `Capture terminée — ${charge.pages} page(s), ${charge.assets} ressource(s).`,
          'ok',
        )
      } else if (statut === 'aborted') {
        push(`Capture interrompue — ${charge.pages} page(s) conservée(s).`, 'warn')
      } else {
        const message =
          typeof charge === 'string' ? charge : charge?.erreur || 'La capture a échoué.'
        push(message, 'error')
      }
    },
    [push],
  )

  const surInjoignable = useCallback(raison => setInjoignable(raison), [])
  const fermerDialogue = useCallback(() => setInjoignable(null), [])

  const { job, start, abort } = useCloneJob({
    onFinish: surFin,
    onUnreachable: surInjoignable,
  })

  const lancer = useCallback(() => {
    const adresse = normalizeUrl(url)
    setUrl(adresse)
    const saisi = Number.parseInt(pagesMax, 10)
    const budget = Number.isFinite(saisi) ? Math.min(Math.max(saisi, 1), PAGES_MAX) : PAGES_DEFAUT
    setPagesMax(String(budget))
    setExpire(false)
    // « Page seule » : le moteur s'arrête après l'adresse saisie, ses styles et
    // ses images étant de toute façon récupérés.
    start(adresse, mode === 'page' ? 1 : budget, cookies.trim(), renduJs)
  }, [url, pagesMax, mode, cookies, renduJs, start])

  // Dernière page réellement écrite, affichée sous la maquette animée.
  const pageCourante = useMemo(() => {
    const dernier = job.events.findLast(e => e.texte.startsWith('Page '))
    return dernier ? dernier.texte.split('—').slice(1).join('—').trim() : ''
  }, [job.events])

  const surExpiration = useCallback(() => setExpire(true), [])

  const source = expire ? '' : previewUrl(job.preview)
  const archive =
    !expire && job.jobId && job.pages > 0 && (job.status === 'done' || job.status === 'aborted')
      ? zipUrl(job.jobId)
      : null

  return (
    <div className="flex min-h-svh flex-col lg:h-svh">
      <TopBar engine={engine} theme={theme} onToggleTheme={toggle} />

      <main className="grid min-h-0 flex-1 grid-rows-[auto_1fr] lg:grid-cols-[340px_1fr] lg:grid-rows-1">
        <aside className="flex min-h-0 flex-col gap-5 overflow-y-auto border-b border-line bg-surface p-4 sm:p-5 lg:border-b-0 lg:border-r">
          <CloneForm
            className="shrink-0"
            url={url}
            onUrlChange={setUrl}
            mode={mode}
            onModeChange={setMode}
            pagesMax={pagesMax}
            onPagesMaxChange={setPagesMax}
            cookies={cookies}
            onCookiesChange={setCookies}
            renduJs={renduJs}
            onRenduJsChange={setRenduJs}
            renduDisponible={renduDisponible}
            status={job.status}
            engineDown={engine === 'down'}
            onSubmit={lancer}
            onAbort={abort}
          />

          <div className="flex shrink-0 flex-col gap-3 border-t border-line pt-3">
            <JobStats job={job} pagesMax={mode === 'page' ? 1 : pagesMax} />
            <RetentionNotice
              key={job.expiresAt ?? 'aucune'}
              expiresAt={job.expiresAt}
              retentionMinutes={Math.round(job.retention / 60)}
              onExpire={surExpiration}
            />
          </div>

          <div className="flex min-h-56 flex-1 shrink-0 flex-col gap-2">
            <h2 className="text-sm font-medium text-ink">Activité</h2>
            <ActivityLog events={job.events} />
          </div>

          <footer className="flex shrink-0 flex-col gap-1.5 text-[11px] text-ink-faint">
            <nav className="flex flex-wrap gap-x-3 gap-y-1">
              <a href="/mentions-legales.html" className="transition-colors hover:text-ink-soft">
                Mentions légales
              </a>
              <a href="/confidentialite.html" className="transition-colors hover:text-ink-soft">
                Confidentialité
              </a>
              <a href="/cgu.html" className="transition-colors hover:text-ink-soft">
                CGU
              </a>
            </nav>
            <p>
              ShyClone 1.0 — <span className="font-mono">mr_shy</span>
            </p>
          </footer>
        </aside>

        <div className="flex min-h-[420px] flex-col p-4 sm:p-5 lg:min-h-0">
          <PreviewPane
            src={source}
            host={hostOf(url)}
            viewport={viewport}
            onViewportChange={setViewport}
            zipHref={archive}
            version={job.status === 'running' ? 'live' : 'final'}
            job={job}
            pageCourante={pageCourante}
          />
        </div>
      </main>

      {injoignable && (
        <UnreachableDialog reason={injoignable} onClose={fermerDialogue} />
      )}
      <Toaster toasts={toasts} onDismiss={dismiss} />
    </div>
  )
}
