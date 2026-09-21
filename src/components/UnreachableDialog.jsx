import { useEffect, useRef } from 'react'

export function UnreachableDialog({ reason, onClose }) {
  const boutonRef = useRef(null)

  useEffect(() => {
    boutonRef.current?.focus()
    const surTouche = e => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', surTouche)
    return () => window.removeEventListener('keydown', surTouche)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div
        className="anim-apparition absolute inset-0 bg-black/55 backdrop-blur-[2px]"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="dlg-titre"
        className="anim-apparition relative z-10 w-full max-w-sm rounded-xl border border-line bg-surface p-5 shadow-2xl"
      >
        <h2 id="dlg-titre" className="text-base font-semibold text-ink">
          Site injoignable
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">{reason}</p>

        <ul className="mt-4 space-y-1.5 border-t border-line pt-4 text-xs text-ink-faint">
          <li>Vérifiez l'orthographe du domaine.</li>
          <li>Le site est peut-être hors ligne ou protégé par un pare-feu.</li>
          <li>Essayez l'adresse complète, avec http:// ou https://.</li>
        </ul>

        <button
          ref={boutonRef}
          type="button"
          onClick={onClose}
          className="mt-5 w-full rounded-md bg-invert-bg px-4 py-2 text-sm font-medium text-invert-ink transition-opacity hover:opacity-90"
        >
          Corriger l'adresse
        </button>
      </div>
    </div>
  )
}
