import React, { forwardRef } from 'react'
import { cn } from '../../utils/helpers'

export const Input = forwardRef(function Input(
  {
    label,
    error,
    helperText,
    icon: Icon,
    className = '',
    id,
    type = 'text',
    disabled = false,
    ...props
  },
  ref
) {
  const inputId = id || (label ? label.toLowerCase().replace(/\s+/g, '-') : undefined)

  return (
    <div className="w-full flex flex-col gap-1.5">
      {label && (
        <label
          htmlFor={inputId}
          className="text-xs font-semibold text-neutral-600 dark:text-neutral-400 tracking-wide select-none"
        >
          {label}
        </label>
      )}
      <div className="relative flex items-center">
        {Icon && (
          <div className="absolute left-3 text-neutral-400 pointer-events-none flex items-center">
            <Icon className="w-4 h-4" />
          </div>
        )}
        <input
          ref={ref}
          id={inputId}
          type={type}
          disabled={disabled}
          className={cn(
            'w-full px-3.5 py-2 text-sm bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 rounded-xl border border-neutral-200 dark:border-neutral-700 placeholder-neutral-400 transition-all duration-150',
            'focus:outline-none focus:border-apple-blue focus:ring-3 focus:ring-apple-blue/20',
            'disabled:bg-neutral-100 dark:disabled:bg-neutral-900 disabled:text-neutral-400 disabled:cursor-not-allowed',
            Icon ? 'pl-9' : '',
            error ? 'border-red-500 focus:border-red-500 focus:ring-red-500/20' : '',
            className
          )}
          {...props}
        />
      </div>
      {error && <p className="text-xs text-red-500 mt-0.5">{error}</p>}
      {!error && helperText && (
        <p className="text-xs text-neutral-500 dark:text-neutral-400">{helperText}</p>
      )}
    </div>
  )
})
