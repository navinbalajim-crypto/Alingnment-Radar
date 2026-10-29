import React from 'react'
import { Button as AriaButton } from 'react-aria-components'
import { cn } from '../../utils/helpers'

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  className = '',
  disabled = false,
  isLoading = false,
  onClick,
  type = 'button',
  ...props
}) {
  const baseClasses =
    'inline-flex items-center justify-center font-medium transition-all duration-150 rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue focus-visible:ring-offset-1 select-none disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer'

  const sizeClasses = {
    sm: 'text-xs px-2.5 py-1.5 gap-1.5',
    md: 'text-sm px-4 py-2 gap-2',
    lg: 'text-base px-5 py-2.5 gap-2.5',
    icon: 'p-2 rounded-lg',
  }[size] || 'text-sm px-4 py-2 gap-2'

  const variantClasses = {
    primary:
      'bg-apple-blue text-white hover:bg-blue-600 active:scale-[0.98] shadow-subtle',
    secondary:
      'bg-neutral-100 text-neutral-900 hover:bg-neutral-200 dark:bg-neutral-800 dark:text-neutral-100 dark:hover:bg-neutral-700 active:scale-[0.98]',
    ghost:
      'text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800/60 active:bg-neutral-200/60',
    outline:
      'border border-neutral-300 dark:border-neutral-700 text-neutral-800 dark:text-neutral-200 hover:bg-neutral-50 dark:hover:bg-neutral-800 active:scale-[0.98]',
    danger:
      'bg-red-500 text-white hover:bg-red-600 active:scale-[0.98] shadow-subtle',
    softDanger:
      'bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-950/40 dark:text-red-400',
  }[variant] || 'bg-apple-blue text-white'

  return (
    <AriaButton
      type={type}
      isDisabled={disabled || isLoading}
      onPress={onClick}
      className={cn(baseClasses, sizeClasses, variantClasses, className)}
      {...props}
    >
      {isLoading ? (
        <>
          <svg
            className="animate-spin -ml-1 mr-2 h-4 w-4 text-current"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8v8H4z"
            />
          </svg>
          <span>Processing...</span>
        </>
      ) : (
        children
      )}
    </AriaButton>
  )
}
