import { useEffect, useState } from 'react'
import { engineHealth } from '../lib/api'

const INTERVALLE = 5000

/** Interroge réellement le moteur : le voyant ne peut plus afficher
 *  « actif » alors que Flask est arrêté. */
export function useEngineHealth() {
  const [state, setState] = useState('unknown')

  useEffect(() => {
    let vivant = true
    const controller = new AbortController()

    const sonder = async () => {
      try {
        await engineHealth(controller.signal)
        if (vivant) setState('up')
      } catch (err) {
        if (vivant && err.name !== 'AbortError') setState('down')
      }
    }

    sonder()
    const id = setInterval(sonder, INTERVALLE)
    return () => {
      vivant = false
      controller.abort()
      clearInterval(id)
    }
  }, [])

  return state
}
