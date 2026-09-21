import { useCallback, useRef, useState } from 'react'

/** Petite file de notifications avec identifiants stables. */
export function useToasts() {
  const [toasts, setToasts] = useState([])
  const compteurRef = useRef(0)

  const push = useCallback((message, tone = 'ok') => {
    const id = ++compteurRef.current
    setToasts(liste => [...liste, { id, message, tone }])
  }, [])

  const dismiss = useCallback(id => {
    setToasts(liste => liste.filter(t => t.id !== id))
  }, [])

  return { toasts, push, dismiss }
}
