import React from 'react'
import { cn } from '../../utils/helpers'

export function Badge({ children, variant = 'neutral', size = 'sm', className = '' }) {
  const sizeClasses = {
    sm: 'text-[11px] px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
  }[size] || 'text-[11px] px-2 py-0.5'

  const variantClasses = {
    neutral: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300',
    blue: 'bg-blue-50 text-blue-700 dark:bg-blue-950/50 dark:text-blue-300 border border-blue-100 dark:border-blue-900/40',
    amber: 'bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300 border border-amber-200 dark:border-amber-800/40',
    emerald: 'bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300 border border-emerald-100 dark:border-emerald-900/40',
    purple: 'bg-purple-50 text-purple-700 dark:bg-purple-950/50 dark:text-purple-300 border border-purple-100 dark:border-purple-900/40',
    rose: 'bg-rose-50 text-rose-700 dark:bg-rose-950/50 dark:text-rose-300 border border-rose-100 dark:border-rose-900/40',
  }[variant] || 'bg-neutral-100 text-neutral-600'

  return (
    <span
      className={cn(
        'inline-flex items-center font-medium rounded-full tracking-wide select-none',
        sizeClasses,
        variantClasses,
        className
      )}
    >
      {children}
    </span>
  )
}
