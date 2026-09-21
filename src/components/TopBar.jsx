import { Moon, Sun } from 'lucide-react'
import { Logo } from './Logo'

const ETATS_MOTEUR = {
  up: { texte: 'Moteur actif', point: 'bg-ok' },
  down: { texte: 'Moteur arrêté', point: 'bg-err anim-battement' },
  unknown: { texte: 'Connexion…', point: 'bg-ink-faint anim-battement' },
}

export function TopBar({ engine, theme, onToggleTheme }) {
  const etat = ETATS_MOTEUR[engine] ?? ETATS_MOTEUR.unknown

  return (
    <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-line bg-surface px-4 sm:px-6">
      <Logo className="h-7 sm:h-8" />

      <div className="flex items-center gap-2">
        <span
          className="flex items-center gap-2 rounded-full border border-line bg-raised px-3 py-1.5 text-xs font-medium text-ink-soft"
          title={engine === 'down' ? 'Lancez le moteur avec npm run dev' : undefined}
        >
          <span className={`inline-block size-2 rounded-full ${etat.point}`} />
          {etat.texte}
        </span>

        <button
          type="button"
          onClick={onToggleTheme}
          aria-label={theme === 'dark' ? 'Passer en thème clair' : 'Passer en thème sombre'}
          className="flex size-9 items-center justify-center rounded-lg border border-line bg-raised text-ink-soft transition-all duration-200 hover:border-line-strong hover:text-ink active:scale-95"
        >
          {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
        </button>
      </div>
    </header>
  )
}
