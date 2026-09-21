import { useCallback, useEffect, useState } from 'react'

const CLE = 'shyclone.theme'

function themeInitial() {
  try {
    const enregistre = localStorage.getItem(CLE)
    if (enregistre === 'dark' || enregistre === 'light') return enregistre
  } catch {
    // localStorage indisponible (navigation privée, iframe cloisonnée)
  }
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

export function useTheme() {
  const [theme, setTheme] = useState(themeInitial)

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    try {
      localStorage.setItem(CLE, theme)
    } catch {
      // idem : l'échec de persistance ne doit pas casser l'affichage
    }
  }, [theme])

  const toggle = useCallback(() => {
    setTheme(t => (t === 'dark' ? 'light' : 'dark'))
  }, [])

  return { theme, toggle }
}
