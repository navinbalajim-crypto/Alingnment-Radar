import React from 'react'
import { Link, useLocation } from 'react-router-dom'
import { Compass, ArrowLeft } from 'lucide-react'

export function LegalNavbar() {
  const location = useLocation()
  const isPrivacy = location.pathname.startsWith('/privacy')
  const isTerms = location.pathname.startsWith('/terms')

  return (
    <header className="sticky top-0 z-40 w-full border-b border-black/[0.06] bg-white/80 backdrop-blur-md dark:border-white/[0.08] dark:bg-neutral-900/80">
      <div className="mx-auto flex h-16 max-w-5xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand */}
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="flex items-center gap-2.5 transition-opacity hover:opacity-80"
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-neutral-900 text-white shadow-subtle dark:bg-white dark:text-neutral-900">
              <Compass className="h-[18px] w-[18px]" />
            </span>
            <span className="text-[16px] font-bold tracking-tight text-neutral-900 dark:text-white">
              Alignment Radar
            </span>
          </Link>

          <Link
            to="/"
            className="hidden items-center gap-1 text-xs font-medium text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-200 sm:inline-flex"
          >
            <ArrowLeft className="h-3.5 w-3.5" />
            <span>Home</span>
          </Link>
        </div>

        {/* Tab switchers */}
        <div className="flex items-center rounded-xl bg-neutral-100 p-1 dark:bg-neutral-800">
          <Link
            to="/privacy"
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              isPrivacy
                ? 'bg-white text-neutral-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                : 'text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white'
            }`}
          >
            Privacy Policy
          </Link>
          <Link
            to="/terms"
            className={`rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
              isTerms
                ? 'bg-white text-neutral-900 shadow-sm dark:bg-neutral-700 dark:text-white'
                : 'text-neutral-600 hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-white'
            }`}
          >
            Terms of Service
          </Link>
        </div>

        {/* Auth CTA */}
        <div className="flex items-center gap-2">
          <Link
            to="/login"
            className="hidden rounded-xl px-3 py-1.5 text-xs font-semibold text-neutral-700 transition-colors hover:bg-neutral-100 dark:text-neutral-300 dark:hover:bg-neutral-800 sm:inline-flex"
          >
            Sign in
          </Link>
          <Link
            to="/register"
            className="rounded-xl bg-apple-blue px-3.5 py-1.5 text-xs font-semibold text-white shadow-subtle transition-colors hover:bg-apple-blue-hover"
          >
            Get Started
          </Link>
        </div>
      </div>
    </header>
  )
}
