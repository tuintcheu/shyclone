// En développement, Vite proxie /api et /preview vers le moteur Flask
// (voir vite.config.js) : l'URL du moteur n'est donc plus codée en dur.
const BASE = import.meta.env.VITE_API_BASE ?? ''
// Renseigné seulement si le moteur est déployé avec SHYCLONE_TOKEN.
const JETON = import.meta.env.VITE_API_TOKEN ?? ''

const ENTETES_AUTH = JETON ? { 'X-ShyClone-Token': JETON } : {}

/* Les liens ouverts par le navigateur (archive .zip) ne peuvent pas porter
   d'en-tête : le jeton passe alors en paramètre d'URL. */
const avecJeton = url =>
  JETON ? `${url}${url.includes('?') ? '&' : '?'}jeton=${encodeURIComponent(JETON)}` : url

async function json(url, options = {}) {
  let res
  try {
    res = await fetch(BASE + url, {
      ...options,
      headers: { ...ENTETES_AUTH, ...(options.headers || {}) },
    })
  } catch (err) {
    if (err.name === 'AbortError') throw err
    // Échec du fetch lui-même : le moteur ne tourne pas. On le distingue d'une
    // réponse d'erreur du moteur pour afficher le bon message.
    const offline = new Error("Service momentanément indisponible. Réessayez dans un instant.")
    offline.offline = true
    throw offline
  }
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    throw new Error(data.message || data.raison || `Le moteur a répondu ${res.status}.`)
  }
  return data
}

const POST_JSON = body => ({
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export function engineHealth(signal) {
  return json('/api/health', { signal })
}

/** Vérifie côté moteur que l'URL répond — un fetch navigateur ne peut pas
 *  distinguer « hors ligne » de « bloqué par CORS ». */
export function checkUrl(url, signal) {
  return json('/api/check', { ...POST_JSON({ url }), signal })
}

export function startClone(url, pagesMax, cookies, renduJs) {
  return json('/api/clone', POST_JSON({
    url, pages_max: pagesMax, cookies, rendu_js: renduJs,
  }))
}

export function fetchJob(jobId, from = 0, signal) {
  return json(`/api/jobs/${jobId}?from=${from}`, { signal })
}

export function abortJob(jobId) {
  return json(`/api/jobs/${jobId}/abort`, { method: 'POST' })
}

export const zipUrl = jobId => avecJeton(`${BASE}/api/jobs/${jobId}/zip`)

/* L'aperçu est servi depuis l'origine du moteur, et surtout pas via le proxy
   Vite : le site capturé s'exécute ainsi sur une origine distincte de celle de
   l'application. On peut alors lui accorder allow-same-origin — indispensable
   pour que ses scripts accèdent à localStorage, donc pour que ses préférences
   (thème sombre, langue, bandeau cookies…) fonctionnent — sans lui donner
   accès au stockage ni au DOM de ShyClone. */
const MOTEUR_DEV = 'http://127.0.0.1:5000'
const PREVIEW_BASE =
  import.meta.env.VITE_PREVIEW_BASE ||
  BASE ||
  (import.meta.env.DEV ? MOTEUR_DEV : '')

export const previewUrl = path => (path ? PREVIEW_BASE + path : '')
