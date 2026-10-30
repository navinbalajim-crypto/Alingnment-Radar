import { Link } from 'react-router-dom'
import { Compass } from 'lucide-react'
import { InteractiveAuthCharacter } from './InteractiveAuthCharacter'

const LIGHT_BG = [
  'radial-gradient(60% 50% at 8% 8%, #fff4e3 0%, rgba(255,244,227,0) 70%)',
  'radial-gradient(42% 46% at 82% 30%, rgba(190,226,247,0.65) 0%, rgba(190,226,247,0) 70%)',
  'radial-gradient(55% 35% at 72% 100%, rgba(208,242,246,0.75) 0%, rgba(208,242,246,0) 70%)',
  'linear-gradient(180deg, #fbf8f2 0%, #f4f6f8 100%)',
].join(', ')

const DARK_BG = [
  'radial-gradient(45% 45% at 82% 32%, rgba(56,124,176,0.22) 0%, rgba(56,124,176,0) 70%)',
  'radial-gradient(55% 35% at 72% 100%, rgba(40,110,130,0.18) 0%, rgba(40,110,130,0) 70%)',
  'linear-gradient(180deg, #0e131a 0%, #0a0e14 100%)',
].join(', ')

export function OrDivider({ label = 'or' }) {
  return (
    <div className="flex items-center gap-3 my-1 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
      <span className="h-px flex-1 bg-black/[0.08] dark:bg-white/[0.1]" />
      {label}
      <span className="h-px flex-1 bg-black/[0.08] dark:bg-white/[0.1]" />
    </div>
  )
}

/**
 * Shared shell for the sign-in and create-account pages: soft full-viewport background,
 * brand + form card on the left, interactive robot on the right (below the form on
 * small screens so it never covers inputs). `overlays` (dialogs) render outside the
 * blurred card, because backdrop-filter would otherwise trap their fixed positioning.
 */
export function AuthLayout({ children, overlays = null }) {
  return (
    <div className="relative min-h-screen overflow-x-hidden">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 dark:hidden" style={{ background: LIGHT_BG }} />
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden dark:block" style={{ background: DARK_BG }} />

      <div className="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-8 px-4 py-8 sm:px-8 md:flex-row md:items-center md:gap-10 lg:gap-16 lg:px-12">
        {/* Left: brand and form */}
        <div className="flex w-full shrink-0 flex-col md:w-[420px] lg:w-[440px]">
          <div className="mb-5 flex items-center gap-2.5 px-1">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-neutral-900 text-white shadow-subtle dark:bg-white dark:text-neutral-900">
              <Compass className="h-[18px] w-[18px]" />
            </div>
            <div>
              <p className="text-base font-bold tracking-tight text-neutral-900 dark:text-white">Alignment Radar</p>
              <p className="text-[10px] font-medium uppercase tracking-wide text-neutral-500">AI Real-Time Messaging</p>
            </div>
          </div>

          <main className="rounded-3xl border border-white/80 bg-white/80 p-7 shadow-[0_24px_60px_-24px_rgba(52,84,118,0.28)] backdrop-blur-xl sm:p-8 dark:border-white/[0.08] dark:bg-neutral-900/80">
            {children}
          </main>

          <div className="mt-4 flex items-center justify-center gap-4 text-xs text-neutral-500 dark:text-neutral-400">
            <Link to="/privacy" className="transition-colors hover:text-neutral-800 underline-offset-4 hover:underline dark:hover:text-white">
              Privacy Policy
            </Link>
            <span className="text-neutral-300 dark:text-neutral-600">•</span>
            <Link to="/terms" className="transition-colors hover:text-neutral-800 underline-offset-4 hover:underline dark:hover:text-white">
              Terms of Service
            </Link>
          </div>
        </div>

        {/* Right: robot companion */}
        <div className="relative flex flex-1 items-center justify-center md:self-stretch">
          <div
            aria-hidden="true"
            className="pointer-events-none absolute left-1/2 top-1/2 hidden aspect-square w-[min(110%,560px)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-gradient-to-b from-sky-100/70 via-cyan-50/40 to-transparent md:block dark:from-sky-400/10 dark:via-cyan-300/5"
          />
          <InteractiveAuthCharacter className="relative h-auto w-36 sm:w-44 md:w-full md:max-w-[300px] lg:max-w-[380px]" />
        </div>
      </div>

      {overlays}
    </div>
  )
}
