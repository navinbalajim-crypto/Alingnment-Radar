/**
 * Generates a unique client-side idempotency ID for chat messages.
 */
export function generateClientId() {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID()
  }
  return 'msg_' + Date.now() + '_' + Math.random().toString(36).substring(2, 11)
}

/**
 * Combines conditional CSS classes cleanly.
 */
export function cn(...classes) {
  return classes.filter(Boolean).join(' ')
}

/**
 * Extracts initials from a user's display name or username.
 */
export function getInitials(name = '') {
  if (!name) return '?'
  const trimmed = name.trim()
  const parts = trimmed.split(/\s+/)
  if (parts.length >= 2) {
    return (parts[0][0] + parts[1][0]).toUpperCase()
  }
  return trimmed.substring(0, 2).toUpperCase()
}

/**
 * Deterministically generates an Apple-style pastel accent color for avatars.
 */
export function getAvatarColor(identifier = '') {
  const colors = [
    'bg-blue-500 text-white',
    'bg-indigo-500 text-white',
    'bg-purple-500 text-white',
    'bg-pink-500 text-white',
    'bg-teal-500 text-white',
    'bg-amber-600 text-white',
    'bg-emerald-600 text-white',
    'bg-sky-600 text-white',
  ]
  let hash = 0
  for (let i = 0; i < identifier.length; i++) {
    hash = identifier.charCodeAt(i) + ((hash << 5) - hash)
  }
  const index = Math.abs(hash) % colors.length
  return colors[index]
}
