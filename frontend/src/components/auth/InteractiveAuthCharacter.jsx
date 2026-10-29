import { useEffect, useRef } from 'react'

// Full-body robot drawn as SVG (viewBox 400 x 600). The eyes are separate layers so they
// can move; their geometry is expressed relative to the face screen ("visor").
const VISOR = { x: 116, y: 120, w: 168, h: 118 }
const EYE_W = 26
const EYE_H = 40
const EYE_CENTERS = [
  { cx: 168, cy: 172 },
  { cx: 232, cy: 172 },
]
const EYES = EYE_CENTERS.map(({ cx, cy }) => ({
  x: ((cx - VISOR.x) / VISOR.w) * 100, // % of visor
  y: ((cy - VISOR.y) / VISOR.h) * 100,
}))
const MAX_X = 75 // max shift, % of eye width
const MAX_Y = 35 // max shift, % of eye height
const REACH = 260 // px distance at which the eyes are fully turned
const SHY = 'translate(-75%, -32%) scaleY(0.85)' // bashful glance away, eyes still open

const STATE = { IDLE: 'idle', FIELD: 'field', PASSWORD: 'password' }

const clamp = (v) => Math.max(-1, Math.min(1, v))

function isTextField(el) {
  return el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement
}

// Uses only the element's type -- never its value.
function stateFor(el) {
  if (!isTextField(el)) return STATE.IDLE
  return el.type === 'password' ? STATE.PASSWORD : STATE.FIELD
}

// Approximate on-screen point the user is typing at. Never called for password
// fields, and only reads the caret index -- not the field's value.
function caretPoint(field) {
  const rect = field.getBoundingClientRect()
  let caret = null
  try {
    caret = field.selectionStart
  } catch {
    caret = null
  }
  const x = caret == null
    ? rect.left + rect.width / 2
    : rect.left + Math.min(rect.width - 12, 36 + caret * 7.5)
  return { x, y: rect.top + rect.height / 2 }
}

const EYE_TRANSFORM_STYLE = { transformBox: 'fill-box', transformOrigin: 'center' }

/**
 * Decorative robot companion for the sign-in / create-account pages.
 * - Idle: the eyes follow the mouse pointer.
 * - A text field (username, email...) has focus: the eyes watch that field and the caret.
 * - A password field has focus: it blushes and looks away. This reacts to focus state
 *   only; password content and length are never read.
 */
export function InteractiveAuthCharacter({ className = '' }) {
  const screenRef = useRef(null)
  const leftEyeRef = useRef(null)
  const rightEyeRef = useRef(null)
  const blushRef = useRef(null)

  useEffect(() => {
    const eyeEls = [leftEyeRef.current, rightEyeRef.current]
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
    let mode = STATE.IDLE
    let frame = 0
    let settleTimer = 0

    const setTransforms = (values) => {
      eyeEls.forEach((el, i) => {
        if (el) el.style.transform = values[i]
      })
    }
    const setBlush = (on) => {
      if (blushRef.current) blushRef.current.style.opacity = on ? '1' : '0'
    }

    const lookAt = ({ x, y }) => {
      const screen = screenRef.current
      if (!screen) return
      const rect = screen.getBoundingClientRect()
      // Each eye aims from its own resting centre, so they move independently.
      setTransforms(
        EYES.map((eye) => {
          const cx = rect.left + (rect.width * eye.x) / 100
          const cy = rect.top + (rect.height * eye.y) / 100
          const tx = clamp((x - cx) / REACH) * MAX_X
          const ty = clamp((y - cy) / REACH) * MAX_Y
          return `translate(${tx.toFixed(1)}%, ${ty.toFixed(1)}%)`
        })
      )
    }

    // Single source of truth: the state is always derived from what is actually focused,
    // so no event ordering (window blur, tab switching, field-to-field moves) can leave
    // the eyes following the mouse while a password field still has focus.
    const sync = () => {
      const el = document.activeElement
      const next = stateFor(el)
      if (next === STATE.PASSWORD) {
        cancelAnimationFrame(frame)
        if (mode !== STATE.PASSWORD) {
          setBlush(true)
          setTransforms([SHY, SHY])
        }
      } else if (next === STATE.FIELD) {
        setBlush(false)
        lookAt(caretPoint(el))
      } else if (mode !== STATE.IDLE) {
        setBlush(false)
        setTransforms(['', ''])
      }
      mode = next
    }

    const onFocusIn = () => {
      clearTimeout(settleTimer)
      sync()
    }
    // During focusout the next element isn't focused yet; resolve once focus settles so a
    // direct username -> password move never passes through the mouse-following state.
    const onFocusOut = () => {
      clearTimeout(settleTimer)
      settleTimer = setTimeout(sync, 0)
    }
    const onInput = (e) => {
      if (mode !== STATE.FIELD || e.target !== document.activeElement) return
      lookAt(caretPoint(e.target))
    }
    // Pointer tracking only ever applies in the idle state, re-checked against the real
    // focus on every move and again inside the animation frame.
    const onPointerMove = (e) => {
      if (reducedMotion || stateFor(document.activeElement) !== STATE.IDLE) return
      const point = { x: e.clientX, y: e.clientY }
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(() => {
        if (stateFor(document.activeElement) === STATE.IDLE) lookAt(point)
      })
    }

    document.addEventListener('focusin', onFocusIn)
    document.addEventListener('focusout', onFocusOut)
    document.addEventListener('input', onInput)
    window.addEventListener('pointermove', onPointerMove, { passive: true })
    // Fields with autoFocus are focused before this effect runs.
    sync()

    return () => {
      clearTimeout(settleTimer)
      cancelAnimationFrame(frame)
      document.removeEventListener('focusin', onFocusIn)
      document.removeEventListener('focusout', onFocusOut)
      document.removeEventListener('input', onInput)
      window.removeEventListener('pointermove', onPointerMove)
    }
  }, [])

  return (
    <svg
      aria-hidden="true"
      focusable="false"
      data-testid="auth-character"
      viewBox="0 0 400 600"
      className={`select-none pointer-events-none overflow-visible ${className}`}
    >
      <defs>
        <linearGradient id="ar-shell" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.55" stopColor="#f1f5fa" />
          <stop offset="1" stopColor="#d6e0ec" />
        </linearGradient>
        <radialGradient id="ar-shell-hi" cx="0.32" cy="0.25" r="0.75">
          <stop offset="0" stopColor="#ffffff" />
          <stop offset="0.6" stopColor="#eef3f9" />
          <stop offset="1" stopColor="#d3deea" />
        </radialGradient>
        <linearGradient id="ar-visor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#1e3149" />
          <stop offset="1" stopColor="#0b1626" />
        </linearGradient>
        <linearGradient id="ar-joint" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#c9d6e4" />
          <stop offset="1" stopColor="#9fb3c8" />
        </linearGradient>
        <linearGradient id="ar-accent" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#3b9cf0" />
          <stop offset="1" stopColor="#1f6fd1" />
        </linearGradient>
        <filter id="ar-glow" x="-80%" y="-80%" width="260%" height="260%">
          <feGaussianBlur stdDeviation="4" result="blur" />
          <feMerge>
            <feMergeNode in="blur" />
            <feMergeNode in="blur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="ar-soft" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="6" />
        </filter>
        <filter id="ar-shadow" x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow dx="0" dy="6" stdDeviation="8" floodColor="#4a6788" floodOpacity="0.18" />
        </filter>
        <clipPath id="ar-visor-clip">
          <rect x={VISOR.x} y={VISOR.y} width={VISOR.w} height={VISOR.h} rx="52" />
        </clipPath>
      </defs>

      {/* Ground shadow */}
      <ellipse cx="200" cy="574" rx="128" ry="14" fill="#5b7895" opacity="0.18" filter="url(#ar-soft)" />

      <g filter="url(#ar-shadow)">
        {/* Legs */}
        <rect x="152" y="430" width="40" height="112" rx="20" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />
        <rect x="208" y="430" width="40" height="112" rx="20" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />
        <rect x="155" y="478" width="34" height="8" rx="4" fill="url(#ar-joint)" opacity="0.55" />
        <rect x="211" y="478" width="34" height="8" rx="4" fill="url(#ar-joint)" opacity="0.55" />
        {/* Feet */}
        <path d="M136 560 q0 -28 30 -28 h22 q14 0 14 14 v14 z" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />
        <path d="M264 560 q0 -28 -30 -28 h-22 q-14 0 -14 14 v14 z" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />

        {/* Arms */}
        <g transform="rotate(14 128 318)">
          <rect x="96" y="306" width="36" height="118" rx="18" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />
          <rect x="99" y="356" width="30" height="7" rx="3.5" fill="url(#ar-joint)" opacity="0.5" />
          <circle cx="114" cy="434" r="19" fill="url(#ar-shell-hi)" stroke="#cdd8e5" strokeWidth="1.5" />
        </g>
        <g transform="rotate(-14 272 318)">
          <rect x="268" y="306" width="36" height="118" rx="18" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />
          <rect x="271" y="356" width="30" height="7" rx="3.5" fill="url(#ar-joint)" opacity="0.5" />
          <circle cx="286" cy="434" r="19" fill="url(#ar-shell-hi)" stroke="#cdd8e5" strokeWidth="1.5" />
        </g>

        {/* Torso and hips */}
        <rect x="140" y="408" width="120" height="44" rx="20" fill="url(#ar-shell)" stroke="#cdd8e5" strokeWidth="1.5" />
        <path
          d="M132 334 q0 -40 44 -40 h48 q44 0 44 40 v58 q0 34 -40 34 h-56 q-40 0 -40 -34 z"
          fill="url(#ar-shell-hi)"
          stroke="#cdd8e5"
          strokeWidth="1.5"
        />
        {/* Collar and tie */}
        <path d="M172 296 L200 326 L228 296 Z" fill="#ffffff" stroke="#d3dde8" strokeWidth="1.5" strokeLinejoin="round" />
        <path d="M194 308 h12 l3 8 -3 4 h-12 l-3 -4 z" fill="url(#ar-accent)" />
        <path d="M195 320 h10 l7 52 -12 14 -12 -14 z" fill="url(#ar-accent)" />

        {/* Neck */}
        <rect x="182" y="266" width="36" height="32" rx="10" fill="url(#ar-joint)" />

        {/* Antenna */}
        <line x1="200" y1="94" x2="200" y2="66" stroke="#b9c8d8" strokeWidth="6" strokeLinecap="round" />
        <circle cx="200" cy="60" r="9" fill="#8fd0ff" stroke="#5aa9e6" strokeWidth="2" />

        {/* Ears */}
        <circle cx="90" cy="184" r="30" fill="url(#ar-shell-hi)" stroke="#cdd8e5" strokeWidth="1.5" />
        <circle cx="90" cy="184" r="17" fill="none" stroke="url(#ar-accent)" strokeWidth="5" opacity="0.75" />
        <circle cx="310" cy="184" r="30" fill="url(#ar-shell-hi)" stroke="#cdd8e5" strokeWidth="1.5" />
        <circle cx="310" cy="184" r="17" fill="none" stroke="url(#ar-accent)" strokeWidth="5" opacity="0.75" />

        {/* Head */}
        <rect x="92" y="90" width="216" height="182" rx="84" fill="url(#ar-shell-hi)" stroke="#cdd8e5" strokeWidth="1.5" />
      </g>

      {/* Face screen */}
      <rect
        ref={screenRef}
        x={VISOR.x}
        y={VISOR.y}
        width={VISOR.w}
        height={VISOR.h}
        rx="52"
        fill="url(#ar-visor)"
      />
      <g clipPath="url(#ar-visor-clip)">
        {/* Blush: shown only while a password field has focus */}
        <g
          ref={blushRef}
          data-testid="auth-character-blush"
          className="transition-opacity duration-300 ease-out motion-reduce:transition-none"
          style={{ opacity: 0 }}
          filter="url(#ar-soft)"
        >
          <ellipse cx="150" cy="206" rx="20" ry="10" fill="#ff8aa1" opacity="0.85" />
          <ellipse cx="250" cy="206" rx="20" ry="10" fill="#ff8aa1" opacity="0.85" />
        </g>

        {EYE_CENTERS.map(({ cx, cy }, i) => (
          <g
            key={i}
            ref={i === 0 ? leftEyeRef : rightEyeRef}
            data-testid="auth-character-eye"
            className="transition-transform duration-300 ease-out motion-reduce:transition-none"
            style={EYE_TRANSFORM_STYLE}
          >
            <rect
              x={cx - EYE_W / 2}
              y={cy - EYE_H / 2}
              width={EYE_W}
              height={EYE_H}
              rx={EYE_W / 2}
              fill="#6ff0ff"
              filter="url(#ar-glow)"
            />
            <rect x={cx - EYE_W / 2 + 6} y={cy - EYE_H / 2 + 6} width="7" height="12" rx="3.5" fill="#ffffff" opacity="0.7" />
          </g>
        ))}

        <path d="M186 210 q14 10 28 0" fill="none" stroke="#6ff0ff" strokeWidth="4" strokeLinecap="round" filter="url(#ar-glow)" />
        {/* Glass reflection */}
        <path d="M130 150 q8 -24 44 -26 h20" fill="none" stroke="#ffffff" strokeOpacity="0.16" strokeWidth="8" strokeLinecap="round" />
      </g>
    </svg>
  )
}
