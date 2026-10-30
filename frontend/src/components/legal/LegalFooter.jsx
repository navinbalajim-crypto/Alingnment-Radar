import React from 'react'
import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'

export function LegalFooter() {
  return (
    <footer className="mt-20 border-t border-black/[0.06] bg-white/60 py-12 dark:border-white/[0.08] dark:bg-neutral-900/60">
      <div className="mx-auto max-w-5xl px-4 sm:px-6 lg:px-8">
        <div className="flex flex-col items-center justify-between gap-6 sm:flex-row">
          <div className="flex items-center gap-2.5">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-neutral-900 text-white dark:bg-white dark:text-neutral-900">
              <Compass className="h-4 w-4" />
            </span>
            <span className="text-sm font-bold tracking-tight text-neutral-900 dark:text-white">
              Alignment Radar
            </span>
            <span className="text-xs text-neutral-400">
              © {new Date().getFullYear()} All rights reserved.
            </span>
          </div>

          <div className="flex flex-wrap items-center justify-center gap-6 text-xs text-neutral-600 dark:text-neutral-400">
            <Link to="/" className="transition-colors hover:text-neutral-900 dark:hover:text-white">
              Home
            </Link>
            <Link to="/privacy" className="transition-colors hover:text-neutral-900 dark:hover:text-white">
              Privacy Policy
            </Link>
            <Link to="/terms" className="transition-colors hover:text-neutral-900 dark:hover:text-white">
              Terms of Service
            </Link>
            <Link to="/login" className="transition-colors hover:text-neutral-900 dark:hover:text-white">
              Sign In
            </Link>
            <a
              href="mailto:support@alignmentradar.com"
              className="transition-colors hover:text-neutral-900 dark:hover:text-white"
            >
              Contact Support
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}

