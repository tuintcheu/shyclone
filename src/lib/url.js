/** Ajoute https:// si l'utilisateur a tapé un domaine nu. */
export function normalizeUrl(raw) {
  const t = raw.trim()
  if (!t) return ''
  return /^https?:\/\//i.test(t) ? t : `https://${t}`
}

export function isValidUrl(value) {
  try {
    const u = new URL(value)
    return (u.protocol === 'http:' || u.protocol === 'https:') && Boolean(u.hostname)
  } catch {
    return false
  }
}

export function hostOf(value) {
  try {
    return new URL(value).hostname
  } catch {
    return ''
  }
}
