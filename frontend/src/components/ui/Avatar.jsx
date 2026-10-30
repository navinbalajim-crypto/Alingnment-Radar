import React, { useEffect, useState } from 'react'
import { getInitials, getAvatarColor, cn, resolveApiUrl } from '../../utils/helpers'
import { Users } from 'lucide-react'

export function Avatar({ name, avatarUrl = null, isGroup = false, size = 'md', className = '' }) {
  const [imgFailed, setImgFailed] = useState(false)

  // Reset the broken-image fallback whenever the picture itself changes
  // (e.g. the user just uploaded a new one, or this card now represents someone else).
  useEffect(() => {
    setImgFailed(false)
  }, [avatarUrl])

  const sizeClasses = {
    sm: 'w-7 h-7 text-xs',
    md: 'w-10 h-10 text-sm font-medium',
    lg: 'w-14 h-14 text-lg font-semibold',
  }[size] || 'w-10 h-10 text-sm font-medium'

  if (isGroup && !avatarUrl) {
    return (
      <div
        className={cn(
          'rounded-full flex items-center justify-center bg-neutral-200 dark:bg-neutral-800 text-neutral-600 dark:text-neutral-300 ring-1 ring-black/5 dark:ring-white/10 shrink-0 select-none',
          sizeClasses,
          className
        )}
      >
        <Users className={size === 'sm' ? 'w-3.5 h-3.5' : size === 'lg' ? 'w-6 h-6' : 'w-5 h-5'} />
      </div>
    )
  }

  if (avatarUrl && !imgFailed) {
    const token = (typeof localStorage !== 'undefined' && localStorage.getItem('ar_access_token')) || ''
    const rawSrc = `${avatarUrl}${avatarUrl.includes('?') ? '&' : '?'}token=${encodeURIComponent(token)}`
    const src = resolveApiUrl(rawSrc)
    return (
      <img
        src={src}
        alt={name || 'User avatar'}
        onError={() => setImgFailed(true)}
        className={cn(
          'rounded-full object-cover shadow-subtle shrink-0 select-none ring-1 ring-black/5 dark:ring-white/10',
          sizeClasses,
          className
        )}
      />
    )
  }

  const initials = getInitials(name)
  const colorClass = getAvatarColor(name || 'user')

  return (
    <div
      className={cn(
        'rounded-full flex items-center justify-center shadow-subtle shrink-0 select-none ring-1 ring-black/5 dark:ring-white/10',
        sizeClasses,
        colorClass,
        className
      )}
      aria-label={name || 'User avatar'}
    >
      <span>{initials}</span>
    </div>
  )
}
