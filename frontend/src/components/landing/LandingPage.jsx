import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Compass } from 'lucide-react'
import { RoomScene, STAGE, MONITOR, PHONE } from './RoomScene'
import {
  StoryChatScreen,
  BrandScreen,
  PhoneScreen,
  PhoneChatPanel,
  ChatVisual,
  AlignmentVisual,
  RoutingVisual,
  VoiceVisual,
  MeetVisual,
  RecommendationsVisual,
  GroupVisual,
  PrivacyVisual,
} from './ScreenMockups'
import './landing.css'

const clamp = (v, lo = 0, hi = 1) => Math.min(hi, Math.max(lo, v))
const smooth = (t) => t * t * (3 - 2 * t)
const lerp = (a, b, t) => a + (b - a) * t

function useMediaQuery(query, fallback = false) {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' && window.matchMedia ? window.matchMedia(query).matches : fallback
  )
  useEffect(() => {
    if (!window.matchMedia) return undefined
    const mql = window.matchMedia(query)
    const onChange = () => setMatches(mql.matches)
    mql.addEventListener?.('change', onChange)
    return () => mql.removeEventListener?.('change', onChange)
  }, [query])
  return matches
}

/* ------------------------------------------------------------------ */
/* Navigation                                                          */
/* ------------------------------------------------------------------ */

function BrandMark({ dark = false }) {
  return (
    <span className="flex items-center gap-2.5">
      <span className={`flex h-8 w-8 items-center justify-center rounded-xl ${dark ? 'bg-white text-neutral-900' : 'bg-neutral-900 text-white'}`}>
        <Compass className="h-[17px] w-[17px]" />
      </span>
      <span className={`text-[15px] font-bold tracking-tight ${dark ? 'hidden text-white sm:inline' : 'text-neutral-900'}`}>Alignment Radar</span>
    </span>
  )
}

function LandingNav() {
  return (
    <header className="fixed inset-x-0 top-0 z-30">
      <nav
        aria-label="Primary"
        className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3 sm:px-8"
      >
        <span className="rounded-2xl bg-black/30 px-2.5 py-1.5 backdrop-blur-md">
          <BrandMark dark />
        </span>
        <span className="flex items-center gap-1.5 rounded-2xl bg-black/30 p-1 backdrop-blur-md">
          <Link to="/login" className="whitespace-nowrap rounded-xl px-2.5 py-1.5 text-[13px] font-medium text-white/90 hover:bg-white/10 hover:text-white sm:px-3 sm:text-sm">
            Sign in
          </Link>
          <Link to="/register" className="whitespace-nowrap rounded-xl bg-white px-2.5 py-1.5 text-[13px] font-semibold text-neutral-900 hover:bg-neutral-100 sm:px-3 sm:text-sm">
            Create account
          </Link>
        </span>
      </nav>
    </header>
  )
}

/* ------------------------------------------------------------------ */
/* Feature content (shared by the in-monitor sequence and the stacked list) */
/* ------------------------------------------------------------------ */

const FEATURES = [
  {
    key: 'chat',
    eyebrow: 'Conversations',
    title: 'More than just chat.',
    body: 'Direct messages and group chats update in real time, with replies, files and images, voice notes and online status.',
    Visual: ChatVisual,
    theme: 'cream',
  },
  {
    key: 'alignment',
    eyebrow: 'Alignment',
    title: 'AI that helps you stay aligned.',
    body: 'Before you send, it flags messages that may leave out key details and suggests a clearer version. After you send, it looks for possible misunderstandings and suggests a clarifying question.',
    note: 'It’s a second pair of eyes, not a final word. You decide what to send.',
    Visual: AlignmentVisual,
    theme: 'sky',
  },
  {
    key: 'routing',
    eyebrow: 'AI routing',
    title: 'Your AI requests, routed sensibly.',
    body: 'Alignment checks and writing help go through an adaptive router that picks NVIDIA or Groq, tries the other once if a provider fails, and can be pinned to a single provider, including Nebius.',
    note: 'If the cloud is unreachable, spelling and clarity suggestions come from a built-in engine.',
    Visual: RoutingVisual,
    theme: 'navy',
  },
  {
    key: 'voice',
    eyebrow: 'Voice messages',
    title: 'Speak. Be heard.',
    body: 'Record voice messages right from the composer. When a speech provider is configured, they’re transcribed, and transcripts can be translated.',
    Visual: VoiceVisual,
    theme: 'cream',
  },
  {
    key: 'meet',
    eyebrow: 'Google Meet',
    title: 'Meet without leaving the chat.',
    body: 'Start a Google Meet call from any conversation. The invitation is posted to the chat so everyone can join.',
    Visual: MeetVisual,
    theme: 'sky',
  },
  {
    key: 'recs',
    eyebrow: 'Recommendations',
    title: 'Relevant, right in the conversation.',
    body: 'When a chat turns to music, videos or places, Alignment Radar can suggest YouTube, Spotify and web results that anyone can share into the chat.',
    Visual: RecommendationsVisual,
    theme: 'cream',
  },
  {
    key: 'groups',
    eyebrow: 'Groups',
    title: 'Stronger together.',
    body: 'Create groups, invite people with a link and manage admins. Everyone sees who’s online and the same alignment checks.',
    Visual: GroupVisual,
    theme: 'sky',
  },
  {
    key: 'privacy',
    eyebrow: 'Privacy & security',
    title: 'Clear about how your data is protected.',
    body: 'Here’s exactly what Alignment Radar does today to protect accounts and conversations.',
    Visual: PrivacyVisual,
    theme: 'teal',
  },
]

const THEMES = {
  cream: { screen: 'linear-gradient(160deg, #fffaf1 0%, #f3f7fa 100%)', dark: false },
  sky: { screen: 'linear-gradient(160deg, #eef7ff 0%, #fbfcff 100%)', dark: false },
  navy: { screen: 'linear-gradient(160deg, #10263c 0%, #0a1523 100%)', dark: true },
  teal: { screen: 'linear-gradient(160deg, #0f2d30 0%, #081b1d 100%)', dark: true },
}

function FeatureText({ feature, index, dark }) {
  return (
    <div>
      <p className={`text-[12px] font-semibold uppercase tracking-[0.18em] ${dark ? 'text-cyan-300' : 'text-[#2f7fd8]'}`}>
        {String(index + 1).padStart(2, '0')} · {feature.eyebrow}
      </p>
      <h2 className={`lp-serif mt-3 text-[30px] leading-[1.1] sm:text-[38px] lg:text-[42px] ${dark ? 'text-white' : 'text-[#10202a]'}`}>
        {feature.title}
      </h2>
      <p className={`mt-4 max-w-md text-[15px] leading-relaxed ${dark ? 'text-white/75' : 'text-neutral-600'}`}>{feature.body}</p>
      {feature.note && (
        <p className={`mt-3 max-w-md text-[13px] leading-relaxed ${dark ? 'text-white/55' : 'text-neutral-500'}`}>{feature.note}</p>
      )}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* The pinned scene: phone -> misunderstanding -> camera moves to the  */
/* monitor -> features play on the monitor (desktop)                   */
/* ------------------------------------------------------------------ */

// Timeline in "units" of scroll, where 1 unit = one viewport height.
const STEP_U = [0.3, 0.75, 1.2, 1.6, 2.0, 3.0] // chat steps 1..6
const FEATURES_U = 3.8 // features begin on the monitor (desktop)
const PANEL_FADE = [2.25, 2.75] // phone chat panel fades as the camera leaves it
const CAPTION_FADE = [3.0, 3.4]
const END_U_DESKTOP = FEATURES_U + FEATURES.length + 0.2
const END_U_MOBILE = 4.1

// Camera keyframes (focus point in stage px, zoom relative to the base fit).
const CAM_START = { u: 0, x: 905, y: 480, z: 1.3 } // on the girl and her phone, monitor fully in frame behind
const CAM_DRIFT = { u: 2.1, x: 915, y: 466, z: 1.45 } // slow push-in while the chat plays out
const CAM_MONITOR_U = 3.45 // camera arrives on the monitor
const CAM_REDUCED = { x: 800, y: 450, z: 1 } // reduced motion: one still wide shot
const MON_CX = MONITOR.x + MONITOR.w / 2
const MON_CY = MONITOR.y + MONITOR.h / 2
const PHONE_CX = PHONE.x + PHONE.w / 2
const PHONE_CY = PHONE.y + PHONE.h / 2

const CAPTIONS = [
  { title: 'Every conversation starts simple.', body: 'A quick message. A quick reply.' },
  { title: 'Until something important goes unsaid.', body: '“The usual one.” Which file? What time? Each person assumes the other knows.' },
  { title: 'Alignment Radar notices what’s missing.', body: 'It points out the gap, so someone can ask instead of guessing.' },
  { title: 'Everyone leaves with the same understanding.', body: 'Both people confirm before it’s marked as clarified.' },
]

function captionFor(step) {
  if (step <= 2) return 0
  if (step <= 4) return 1
  if (step === 5) return 2
  return 3
}

function moodFor(step) {
  if (step === 3 || step === 4) return 'puzzled'
  if (step === 5) return 'watching'
  if (step >= 6) return 'relieved'
  return 'calm'
}

function StoryScene({ reduced, desktop }) {
  const containerRef = useRef(null)
  const stickyRef = useRef(null)
  const worldRef = useRef(null)
  const canvasRef = useRef(null)
  const panelRef = useRef(null)
  const captionRef = useRef(null)
  const heroRef = useRef(null)
  const vignetteRef = useRef(null)
  const [step, setStep] = useState(reduced ? 6 : 0)
  const [feature, setFeature] = useState(-1)
  const stateRef = useRef({ step: reduced ? 6 : 0, feature: -1, canvasScale: 0 })

  const endU = desktop ? END_U_DESKTOP : END_U_MOBILE
  const showFeaturesInMonitor = desktop && !reduced

  useEffect(() => {
    let raf = 0
    const update = () => {
      raf = 0
      const container = containerRef.current
      const sticky = stickyRef.current
      const world = worldRef.current
      if (!container || !sticky || !world) return

      const vw = sticky.clientWidth
      const vh = sticky.clientHeight
      const u = reduced ? 0 : clamp(-container.getBoundingClientRect().top / vh, 0, endU)

      // Base fit of the 1600x900 stage: cover on wide screens, a cinematic band on phones.
      const mobile = vw < 768
      const k = mobile ? (vw * 1.6) / STAGE.w : Math.max(vw / STAGE.w, vh / STAGE.h)

      // Final camera: the monitor (with its bezel) fills the view below the nav bar.
      const finalScale = mobile
        ? (vw * 0.96) / (MONITOR.w + 28)
        : Math.min((vw * 0.94) / (MONITOR.w + 28), (vh - 96) / (MONITOR.h + 28))
      const finalCenterY = mobile ? vh * 0.5 : vh / 2 + 22

      // Camera position along the keyframes: one continuous move, reversible with scroll.
      let fx
      let fy
      let s
      let cy = vh / 2
      if (reduced) {
        fx = CAM_REDUCED.x
        fy = CAM_REDUCED.y
        s = k * CAM_REDUCED.z
      } else if (u <= CAM_DRIFT.u) {
        const t = u / CAM_DRIFT.u
        fx = lerp(CAM_START.x, CAM_DRIFT.x, t)
        fy = lerp(CAM_START.y, CAM_DRIFT.y, t)
        s = k * lerp(CAM_START.z, CAM_DRIFT.z, t)
      } else {
        const t = smooth(clamp((u - CAM_DRIFT.u) / (CAM_MONITOR_U - CAM_DRIFT.u)))
        fx = lerp(CAM_DRIFT.x, MON_CX, t)
        fy = lerp(CAM_DRIFT.y, MON_CY, t)
        // Zoom in log space so the push-in feels like a steady dolly, not a jump.
        const s0 = k * CAM_DRIFT.z
        s = s0 * Math.pow(finalScale / s0, t)
        cy = lerp(vh / 2, finalCenterY, t)
      }
      const tx = vw / 2 - s * fx
      const ty = cy - s * fy
      world.style.transform = `translate(${tx}px, ${ty}px) scale(${s})`

      // Feature canvas renders at exactly 1:1 once the camera has arrived (crisp text).
      if (canvasRef.current && stateRef.current.canvasScale !== finalScale) {
        stateRef.current.canvasScale = finalScale
        const c = canvasRef.current
        c.style.width = `${MONITOR.w * finalScale}px`
        c.style.height = `${MONITOR.h * finalScale}px`
        c.style.transform = `scale(${1 / finalScale})`
      }

      // Phone chat panel follows the phone on screen, then fades as the camera leaves.
      if (panelRef.current) {
        const panel = panelRef.current
        const px = tx + s * PHONE_CX
        const py = ty + s * PHONE_CY
        const left = mobile ? vw / 2 - 124 : Math.min(vw - 264, px + 34)
        const top = mobile ? 72 : Math.max(72, py - 236)
        panel.style.transform = `translate(${left}px, ${top}px)`
        const visible = reduced ? 1 : u >= STEP_U[0] - 0.1 ? 1 - clamp((u - PANEL_FADE[0]) / (PANEL_FADE[1] - PANEL_FADE[0])) : 0
        panel.style.opacity = String(visible)
      }

      if (heroRef.current) heroRef.current.style.opacity = String(reduced ? 0 : 1 - clamp(u / 0.25))
      if (captionRef.current) {
        captionRef.current.style.opacity = String(reduced ? 1 : 1 - clamp((u - CAPTION_FADE[0]) / (CAPTION_FADE[1] - CAPTION_FADE[0])))
      }
      if (vignetteRef.current) {
        const t = clamp((u - CAM_DRIFT.u) / (CAM_MONITOR_U - CAM_DRIFT.u))
        vignetteRef.current.style.opacity = String(0.3 + 0.6 * t)
      }

      // Discrete story state: only re-render React when the step or feature changes.
      let nextStep = reduced ? 6 : STEP_U.filter((at) => u >= at).length
      if (!reduced && u >= FEATURES_U - 0.25) nextStep = 7
      const nextFeature = showFeaturesInMonitor && u >= FEATURES_U - 0.25
        ? Math.min(FEATURES.length - 1, Math.max(0, Math.floor(u - FEATURES_U)))
        : -1
      if (nextStep !== stateRef.current.step) {
        stateRef.current.step = nextStep
        setStep(nextStep)
      }
      if (nextFeature !== stateRef.current.feature) {
        stateRef.current.feature = nextFeature
        setFeature(nextFeature)
      }
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [reduced, endU, showFeaturesInMonitor])

  const caption = CAPTIONS[captionFor(step)]
  const featureTheme = feature >= 0 ? THEMES[FEATURES[feature].theme] : null

  return (
    <section
      ref={containerRef}
      aria-label="Story: a conversation that goes slightly wrong"
      className="relative"
      style={{ height: reduced ? '100svh' : `${(endU + 1) * 100}svh` }}
    >
      {/* The story as text, for screen readers (the artwork itself is decorative). */}
      <ol className="sr-only">
        <li>A young woman is chatting with Arjun on her phone. He writes: “Send it tomorrow.”</li>
        <li>She asks: “Which file, and what time?” He replies: “The usual one.”</li>
        <li>She is left unsure. On the monitor behind her, Alignment Radar flags a possible misunderstanding: the file and the time are missing.</li>
        <li>Arjun clarifies: “The budget sheet, by 10 AM.” Both confirm, and the issue is marked as clarified.</li>
      </ol>

      <div ref={stickyRef} className="sticky top-0 h-[100svh] overflow-hidden bg-[#0b1215]" data-mood={moodFor(step)}>
        <div ref={worldRef} className="absolute left-0 top-0 origin-top-left" style={{ width: STAGE.w, height: STAGE.h }}>
          <RoomScene />

          {/* Live phone screen, layered on the phone she is holding */}
          <div
            aria-hidden="true"
            className="absolute overflow-hidden rounded-[4px]"
            style={{
              left: PHONE.x,
              top: PHONE.y,
              width: PHONE.w,
              height: PHONE.h,
              transform: `rotate(${PHONE.rot}deg)`,
            }}
          >
            <PhoneScreen step={step} />
          </div>

          {/* Monitor screen: the story chat, then (desktop) the feature sequence */}
          <div className="absolute overflow-hidden rounded-[6px]" style={{ left: MONITOR.x, top: MONITOR.y, width: MONITOR.w, height: MONITOR.h }}>
            <div aria-hidden="true" className="absolute inset-0">
              <StoryChatScreen step={step} />
            </div>
            {!showFeaturesInMonitor && (
              <div aria-hidden="true" className={`absolute inset-0 transition-opacity duration-700 ${step >= 7 ? 'opacity-100' : 'opacity-0'}`}>
                <BrandScreen />
              </div>
            )}
            {showFeaturesInMonitor && (
              <div
                ref={canvasRef}
                data-testid="monitor-features"
                className={`absolute left-0 top-0 origin-top-left transition-opacity duration-700 ${feature >= 0 ? 'opacity-100' : 'opacity-0'}`}
                style={{ background: featureTheme ? featureTheme.screen : '#0b1215' }}
              >
                {FEATURES.map((f, i) => (
                  <div
                    key={f.key}
                    className={`absolute inset-0 grid grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] items-center gap-10 px-[6%] transition-all duration-700 ease-out ${
                      i === feature ? 'opacity-100' : 'pointer-events-none translate-y-6 opacity-0'
                    }`}
                  >
                    <FeatureText feature={f} index={i} dark={THEMES[f.theme].dark} />
                    <div className="flex justify-center">
                      <f.Visual />
                    </div>
                  </div>
                ))}
                <ol className="absolute bottom-5 left-[6%] flex items-center gap-1.5" aria-label="Feature progress">
                  {FEATURES.map((f, i) => (
                    <li
                      key={f.key}
                      aria-current={i === feature ? 'step' : undefined}
                      className={`h-1.5 rounded-full transition-all duration-500 ${i === feature ? 'w-6' : 'w-1.5'} ${
                        featureTheme?.dark ? (i === feature ? 'bg-cyan-300' : 'bg-white/25') : i === feature ? 'bg-[#2f7fd8]' : 'bg-neutral-300'
                      }`}
                    >
                      <span className="sr-only">{f.eyebrow}</span>
                    </li>
                  ))}
                </ol>
              </div>
            )}
          </div>
        </div>

        <div
          ref={vignetteRef}
          aria-hidden="true"
          className="pointer-events-none absolute inset-0"
          style={{ background: 'radial-gradient(120% 90% at 50% 50%, rgba(0,0,0,0) 55%, rgba(4,8,10,0.92) 100%)' }}
        />

        {/* Readable copy of the phone conversation, pinned beside the phone */}
        <div ref={panelRef} aria-hidden="true" className="pointer-events-none absolute left-0 top-0 opacity-0" data-testid="phone-chat-panel">
          <PhoneChatPanel step={step} />
        </div>

        {/* Opening headline */}
        <div
          ref={heroRef}
          className="pointer-events-none absolute inset-0 px-4 pt-[12vh] sm:px-8 md:pt-[18vh]"
          style={{ background: 'linear-gradient(90deg, rgba(5,10,12,0.82) 0%, rgba(5,10,12,0.55) 34%, rgba(5,10,12,0) 58%)' }}
        >
          <div className="mx-auto max-w-6xl">
            <h1 className="lp-serif max-w-[30rem] text-[30px] leading-[1.08] text-white drop-shadow-[0_2px_18px_rgba(0,0,0,0.6)] sm:text-5xl md:text-[52px]">
              Most misunderstandings start with a message that seemed clear.
            </h1>
            <p className="mt-4 text-[13px] uppercase tracking-[0.2em] text-white/70">Scroll to follow the conversation</p>
          </div>
        </div>

        {/* Story captions */}
        <div ref={captionRef} aria-hidden="true" className="pointer-events-none absolute inset-x-0 bottom-[3%] px-4 sm:px-8 md:bottom-[6%]">
          <div className="mx-auto max-w-6xl">
            <div
              key={caption.title}
              className={`lp-msg-in max-w-md rounded-2xl bg-black/50 p-3.5 backdrop-blur-sm sm:p-5 ${step === 0 ? 'invisible' : ''}`}
            >
              <p className="lp-serif text-lg text-white sm:text-2xl">{caption.title}</p>
              <p className="mt-1 text-[13px] text-white/75 sm:text-sm">{caption.body}</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Stacked feature screens: phones, and anyone who prefers reduced motion */
/* ------------------------------------------------------------------ */

function StackedFeatures({ alwaysVisible }) {
  return (
    <section aria-label="Features" className={`bg-[#0b1215] px-3 pb-6 pt-2 ${alwaysVisible ? 'md:px-8' : 'md:hidden'}`}>
      <div className={alwaysVisible ? 'mx-auto max-w-5xl' : ''}>
        {FEATURES.map((f, i) => {
          const t = THEMES[f.theme]
          return (
            <div key={f.key} className="mb-4 rounded-[24px] border border-[#2a323b] bg-[#161b21] p-2">
              <div
                className={`flex flex-col gap-6 rounded-[18px] px-5 py-8 ${alwaysVisible ? 'md:grid md:grid-cols-2 md:items-center md:px-10 md:py-12' : ''}`}
                style={{ background: t.screen }}
              >
                <FeatureText feature={f} index={i} dark={t.dark} />
                <div className="flex justify-center">
                  <f.Visual />
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ */
/* Closing                                                             */
/* ------------------------------------------------------------------ */

function ClosingSection() {
  return (
    <section
      aria-labelledby="lp-closing-title"
      className="relative overflow-hidden px-4 py-24 sm:px-8 sm:py-32"
      style={{
        background:
          'radial-gradient(70% 60% at 50% 0%, rgba(52,211,232,0.16) 0%, rgba(52,211,232,0) 70%), linear-gradient(180deg, #0b1215 0%, #102127 38%, #f6efe4 38.1%, #fbf7f0 100%)',
      }}
    >
      <div className="mx-auto max-w-3xl rounded-[32px] border border-black/[0.06] bg-[#fffdf9] px-6 py-14 text-center shadow-[0_40px_100px_-50px_rgba(16,32,42,0.55)] sm:px-14">
        <div className="flex justify-center">
          <BrandMark />
        </div>
        <h2 id="lp-closing-title" className="lp-serif mx-auto mt-8 max-w-xl text-[32px] leading-[1.12] text-[#10202a] sm:text-[44px]">
          Better conversations start with better understanding.
        </h2>
        <p className="mx-auto mt-4 max-w-md text-[15px] text-neutral-600">
          Bring clarity to your conversations with Alignment Radar.
        </p>
        <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            to="/register"
            className="inline-flex items-center gap-2 rounded-xl bg-[#007AFF] px-5 py-3 text-sm font-semibold text-white shadow-subtle hover:bg-[#0062CC] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#007AFF] focus-visible:ring-offset-2"
          >
            Create your account <ArrowRight className="h-4 w-4" />
          </Link>
          <Link
            to="/login"
            className="inline-flex items-center rounded-xl border border-black/10 bg-white px-5 py-3 text-sm font-semibold text-neutral-800 hover:bg-neutral-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#007AFF] focus-visible:ring-offset-2"
          >
            Sign in
          </Link>
        </div>
      </div>
      <p className="mt-10 text-center text-xs text-neutral-500">© {new Date().getFullYear()} Alignment Radar</p>
    </section>
  )
}

export function LandingPage() {
  const reduced = useMediaQuery('(prefers-reduced-motion: reduce)')
  const desktop = useMediaQuery('(min-width: 768px)', true)

  // The app shell sets `body { overflow: hidden }` (index.css) so the chat UI stays
  // full-screen. The landing page needs normal page scrolling and a scrollbar, so
  // re-enable it while this page is mounted and restore it on the way out.
  useEffect(() => {
    const previous = document.body.style.overflowY
    document.body.style.overflowY = 'auto'
    return () => {
      document.body.style.overflowY = previous
    }
  }, [])
  return (
    <div className="alignment-landing">
      <LandingNav />
      <main>
        <StoryScene reduced={reduced} desktop={desktop} />
        {/* Desktop features play inside the monitor; phones and reduced motion get the stacked screens. */}
        {(reduced || !desktop) && <StackedFeatures alwaysVisible={reduced} />}
        <ClosingSection />
      </main>
    </div>
  )
}
