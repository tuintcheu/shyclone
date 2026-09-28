import { useCallback, useEffect, useRef, useState } from 'react'
import { abortJob, checkUrl, fetchJob, startClone } from '../lib/api'

const POLL_MS = 1000
const ECHECS_TOLERES = 5

const ETAT_INITIAL = {
  status: 'idle',   // idle | checking | running | done | aborted | error
  jobId: null,
  pages: 0,
  assets: 0,
  bytes: 0,
  duration: 0,
  preview: null,
  error: null,
  expiresAt: null,
  retention: 13 * 60,
  events: [],
}

const TERMINAUX = new Set(['done', 'aborted', 'error'])

/**
 * Machine à états d'une capture : vérification de l'URL, lancement du job,
 * puis suivi par polling du journal renvoyé par le moteur.
 */
export function useCloneJob({ onFinish, onUnreachable } = {}) {
  const [job, setJob] = useState(ETAT_INITIAL)
  const pollRef = useRef(null)
  const curseurRef = useRef(0)
  const echecsRef = useRef(0)
  const jobRef = useRef(null)

  const arreterPolling = useCallback(() => {
    clearInterval(pollRef.current)
    pollRef.current = null
  }, [])

  useEffect(() => arreterPolling, [arreterPolling])

  const sonder = useCallback(async () => {
    const id = jobRef.current
    if (!id) return
    let data
    try {
      data = await fetchJob(id, curseurRef.current)
      echecsRef.current = 0
    } catch {
      // Un aller-retour raté n'est pas fatal ; plusieurs de suite, si.
      if (++echecsRef.current < ECHECS_TOLERES) return
      arreterPolling()
      setJob(j => ({ ...j, status: 'error', error: 'Contact perdu avec le moteur.' }))
      onFinish?.('error', 'Contact perdu avec le moteur.')
      return
    }

    curseurRef.current = data.curseur
    const termine = TERMINAUX.has(data.statut)

    setJob(j => ({
      ...j,
      status: termine ? data.statut : 'running',
      pages: data.pages,
      assets: data.assets,
      bytes: data.octets,
      duration: data.duree,
      error: data.erreur,
      retention: data.retention ?? j.retention,
      // Converti en date absolue : le polling s'arrête quand le job se termine,
      // le décompte doit continuer côté client.
      expiresAt:
        data.expire_dans != null ? Date.now() + data.expire_dans * 1000 : j.expiresAt,
      // Dès la première page écrite : inutile de faire patienter devant un
      // panneau vide pendant qu'un site de 500 pages se capture.
      preview: data.pages > 0 ? data.preview : null,
      events: data.evenements.length ? [...j.events, ...data.evenements] : j.events,
    }))

    if (termine) {
      arreterPolling()
      onFinish?.(data.statut, data)
    }
  }, [arreterPolling, onFinish])

  const start = useCallback(async (url, pagesMax, cookies) => {
    arreterPolling()
    curseurRef.current = 0
    echecsRef.current = 0
    jobRef.current = null
    setJob({ ...ETAT_INITIAL, status: 'checking' })

    try {
      const verif = await checkUrl(url)
      if (!verif.ok) {
        setJob(ETAT_INITIAL)
        onUnreachable?.(verif.raison || "Le site n'a pas répondu.")
        return
      }
      const { job_id: id } = await startClone(url, pagesMax, cookies)
      jobRef.current = id
      setJob(j => ({ ...j, status: 'running', jobId: id }))
      pollRef.current = setInterval(sonder, POLL_MS)
      sonder()
    } catch (err) {
      const message = err.message || 'Échec du lancement.'
      setJob({ ...ETAT_INITIAL, status: 'error', error: message })
      onFinish?.('error', message)
    }
  }, [arreterPolling, onFinish, onUnreachable, sonder])

  const abort = useCallback(async () => {
    if (!jobRef.current) return
    try {
      await abortJob(jobRef.current)
    } catch {
      // Le moteur s'arrêtera de lui-même ; le polling constatera l'état final.
    }
  }, [])

  const reset = useCallback(() => {
    arreterPolling()
    jobRef.current = null
    setJob(ETAT_INITIAL)
  }, [arreterPolling])

  const busy = job.status === 'checking' || job.status === 'running'
  return { job, busy, start, abort, reset }
}
