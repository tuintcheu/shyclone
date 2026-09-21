import { useEffect, useRef, useState } from 'react'

const DUREE = 420

/** Fait défiler un nombre jusqu'à sa nouvelle valeur au lieu de le faire sauter. */
export function useCompteurAnime(valeur) {
  const [affiche, setAffiche] = useState(valeur)
  const departRef = useRef(valeur)
  const animRef = useRef(0)

  useEffect(() => {
    const depart = departRef.current
    if (depart === valeur) return
    const t0 = performance.now()

    const tick = maintenant => {
      const p = Math.min(1, (maintenant - t0) / DUREE)
      const adouci = 1 - (1 - p) ** 3
      const courant = Math.round(depart + (valeur - depart) * adouci)
      setAffiche(courant)
      if (p < 1) animRef.current = requestAnimationFrame(tick)
      else departRef.current = valeur
    }

    animRef.current = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(animRef.current)
  }, [valeur])

  return affiche
}
