/** Durée en secondes → « 1 min 04 s » ou « 12,3 s ». */
export function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds.toFixed(1).replace('.', ',')} s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m} min ${String(s).padStart(2, '0')} s`
}

/** Octets → « 1,4 Mo ». */
export function formatBytes(bytes) {
  if (!bytes) return '0 o'
  const unites = ['o', 'ko', 'Mo', 'Go']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), unites.length - 1)
  const valeur = bytes / 1024 ** i
  return `${valeur.toFixed(i === 0 ? 0 : 1).replace('.', ',')} ${unites[i]}`
}

/** Secondes écoulées depuis le début du job → « 0:04 ». */
export function formatStamp(seconds) {
  const s = Math.floor(seconds)
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}
