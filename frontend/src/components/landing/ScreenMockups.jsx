import {
  AlertTriangle,
  Check,
  Compass,
  Cpu,
  FileText,
  Globe,
  KeyRound,
  Languages,
  Lock,
  Mail,
  MessageSquare,
  Play,
  Share2,
  ShieldCheck,
  Sparkles,
  ToggleRight,
  Users,
  Video,
} from 'lucide-react'

// Illustrative product mock-ups. They mirror the real app's UI (soft blue outgoing
// bubbles, amber pre-send warning, alignment finding card, Meet invitation, presence
// count) but are static demonstrations: nothing here is interactive or live.

function Bubble({ out, children, className = '' }) {
  return (
    <div className={`flex ${out ? 'justify-end' : 'justify-start'} lp-msg-in ${className}`}>
      <div
        className={`max-w-[78%] rounded-2xl px-3 py-1.5 text-[11px] leading-snug shadow-sm ${
          out ? 'rounded-br-sm bg-[#3D72B0] text-white' : 'rounded-bl-sm border border-black/[0.05] bg-white text-neutral-800'
        }`}
      >
        {children}
      </div>
    </div>
  )
}

function Initials({ text, className = '' }) {
  return (
    <span className={`inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white ${className}`}>
      {text}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Story monitor (inside the illustrated room, 452 x 276 stage px)     */
/* ------------------------------------------------------------------ */

export function StoryChatScreen({ step }) {
  const show = (n) => step >= n
  const resolved = step >= 6
  return (
    <div className="flex h-full w-full flex-col bg-[#f4f6f9] text-left">
      <div className="flex items-center gap-2 border-b border-black/[0.06] bg-white/90 px-3 py-1.5">
        <Initials text="AK" className="h-5 w-5 bg-teal-600 text-[8px]" />
        <div className="leading-tight">
          <p className="text-[10px] font-semibold text-neutral-900">Arjun</p>
          <p className="flex items-center gap-1 text-[8px] text-emerald-600">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" /> Online
          </p>
        </div>
        <span className="ml-auto flex items-center gap-1 rounded-full bg-neutral-100 px-1.5 py-0.5 text-[7.5px] font-medium text-neutral-500">
          <Compass className="h-2.5 w-2.5" /> Alignment Radar
        </span>
      </div>

      <div className="flex flex-1 flex-col justify-end gap-1.5 overflow-hidden px-3 py-2">
        {show(1) && <Bubble>Send it tomorrow.</Bubble>}
        {show(2) && <Bubble out>Which file, and what time?</Bubble>}
        {show(3) && <Bubble>The usual one.</Bubble>}
        {show(5) && (
          <div
            className={`lp-msg-in rounded-xl border bg-white px-2.5 py-1.5 shadow-sm transition-colors ${
              resolved ? 'border-emerald-200' : 'border-amber-300'
            }`}
          >
            <div className="flex items-center gap-1 text-[9px] font-semibold">
              {resolved ? (
                <span className="flex items-center gap-1 text-emerald-700">
                  <Check className="h-3 w-3" /> Clarified, both of you confirmed
                </span>
              ) : (
                <span className="flex items-center gap-1 text-amber-800">
                  <AlertTriangle className="h-3 w-3" /> Possible misunderstanding
                </span>
              )}
            </div>
            {!resolved && (
              <>
                <p className="mt-0.5 text-[8.5px] leading-snug text-neutral-600">
                  &ldquo;Send it tomorrow&rdquo; doesn&apos;t say which file or when it&apos;s due.
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[7.5px] font-medium text-amber-900">Missing: which file</span>
                  <span className="rounded-md bg-amber-100 px-1.5 py-0.5 text-[7.5px] font-medium text-amber-900">Missing: exact time</span>
                  <span className="ml-auto rounded-md bg-neutral-900 px-1.5 py-0.5 text-[7.5px] font-medium text-white">Ask for clarification</span>
                </div>
              </>
            )}
          </div>
        )}
        {show(6) && <Bubble>The budget sheet, by 10 AM.</Bubble>}
      </div>

      <div className="mx-3 mb-2 flex items-center rounded-full border border-black/[0.06] bg-white px-2.5 py-1 text-[8.5px] text-neutral-400">
        Type a message or ask for alignment…
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* The girl's phone                                                    */
/* ------------------------------------------------------------------ */

// Tiny bubbles drawn on the phone itself (stage-scale, decorative).
export function PhoneScreen({ step }) {
  const pill = (out, w) => (
    <div className={`flex ${out ? 'justify-end' : 'justify-start'} lp-msg-in`}>
      <div className={`h-[4px] rounded-full ${out ? 'bg-[#3D72B0]' : 'bg-white'}`} style={{ width: w }} />
    </div>
  )
  return (
    <div className="flex h-full w-full flex-col justify-end gap-[3px] bg-[#e8eef3] p-[3px]">
      {step >= 1 && pill(false, 16)}
      {step >= 2 && pill(true, 20)}
      {step >= 3 && pill(false, 12)}
      {step >= 4 && step < 6 && <div className="h-[4px] w-[4px] self-end rounded-full bg-amber-500" />}
    </div>
  )
}

// The readable version of the phone conversation, attached to the phone like the
// floating chat panel in the reference storyboard.
export function PhoneChatPanel({ step }) {
  const puzzled = step === 4
  return (
    <div className="w-[248px] rounded-[22px] border border-white/15 bg-[#0f171c]/85 p-3 shadow-[0_24px_60px_-20px_rgba(0,0,0,0.8)] backdrop-blur-md">
      <div className="mb-2 flex items-center gap-2 px-1">
        <Initials text="AK" className="h-6 w-6 bg-teal-600 text-[9px]" />
        <div className="leading-tight">
          <p className="text-[12px] font-semibold text-white">Arjun</p>
          <p className="text-[10px] text-white/50">on her phone</p>
        </div>
      </div>
      <div className="flex flex-col gap-1.5 rounded-2xl bg-[#eef2f6] p-2.5">
        {step >= 1 && <Bubble>Send it tomorrow.</Bubble>}
        {step >= 2 && <Bubble out>Which file, and what time?</Bubble>}
        {step >= 3 && <Bubble>The usual one.</Bubble>}
        {puzzled && (
          <div className="flex justify-end lp-msg-in">
            <span className="rounded-full bg-white px-2.5 py-1 text-[13px] leading-none tracking-widest text-neutral-400">…?</span>
          </div>
        )}
        {step >= 5 && (
          <div className="lp-msg-in flex items-center gap-1.5 rounded-xl border border-amber-300 bg-amber-50 px-2 py-1.5 text-[10.5px] font-medium text-amber-900">
            <AlertTriangle className="h-3 w-3 shrink-0 text-amber-600" /> Something important is missing
          </div>
        )}
      </div>
    </div>
  )
}

export function BrandScreen() {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center bg-gradient-to-b from-[#0f1d24] to-[#081015] text-center">
      <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-white text-neutral-900">
        <Compass className="h-5 w-5" />
      </div>
      <p className="lp-serif mt-2 text-[20px] text-white">Alignment Radar</p>
      <p className="mt-0.5 text-[8px] uppercase tracking-[0.18em] text-cyan-200/80">Here&apos;s how it helps</p>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Feature visuals (real-size, inside the full-screen monitor)         */
/* ------------------------------------------------------------------ */

const card = 'rounded-2xl border border-black/[0.06] bg-white shadow-[0_18px_40px_-24px_rgba(20,40,60,0.45)]'

export function ChatVisual() {
  const chats = [
    { n: 'Arjun Kumar', p: 'The budget sheet, by 10 AM.', c: 'bg-teal-600', on: true },
    { n: 'Design Review', p: 'Mira: shared the new flow', c: 'bg-sky-600', group: true },
    { n: 'Lena Ortiz', p: 'Voice message · 0:24', c: 'bg-amber-600' },
  ]
  return (
    <div className={`${card} flex h-[300px] w-full max-w-[520px] overflow-hidden`}>
      <div className="hidden w-[42%] border-r border-black/[0.06] bg-neutral-50 p-2 sm:block">
        <p className="px-2 pb-2 text-[11px] font-semibold text-neutral-500">Direct messages</p>
        {chats.map((c, i) => (
          <div key={c.n} className={`flex items-center gap-2 rounded-xl px-2 py-2 ${i === 0 ? 'bg-neutral-200/70' : ''}`}>
            <span className="relative">
              <Initials text={c.n.split(' ').map((w) => w[0]).join('')} className={`h-8 w-8 text-[10px] ${c.c}`} />
              {c.on && <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full bg-emerald-500 ring-2 ring-neutral-50" />}
            </span>
            <span className="min-w-0">
              <span className="block truncate text-[12px] font-medium text-neutral-900">{c.n}</span>
              <span className="block truncate text-[10.5px] text-neutral-500">{c.p}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="flex flex-1 flex-col bg-[#f4f6f9]">
        <div className="flex items-center gap-2 border-b border-black/[0.06] bg-white px-3 py-2">
          <Initials text="AK" className="h-7 w-7 bg-teal-600 text-[10px]" />
          <div className="leading-tight">
            <p className="text-[12px] font-semibold text-neutral-900">Arjun Kumar</p>
            <p className="text-[10px] text-emerald-600">Online</p>
          </div>
        </div>
        <div className="flex flex-1 flex-col justify-end gap-2 p-3">
          <Bubble>Can you share the report before standup?</Bubble>
          <Bubble out>Yes, I&apos;ll send it by 9:30.</Bubble>
          <div className="flex justify-end">
            <div className="flex items-center gap-2 rounded-2xl rounded-br-sm bg-[#3D72B0] px-3 py-2 text-[11px] text-white">
              <FileText className="h-3.5 w-3.5" /> Q3-report.pdf
            </div>
          </div>
        </div>
        <div className="m-3 mt-0 rounded-full border border-black/[0.06] bg-white px-3 py-1.5 text-[10.5px] text-neutral-400">
          Type a message or ask for alignment…
        </div>
      </div>
    </div>
  )
}

export function AlignmentVisual() {
  return (
    <div className="flex w-full max-w-[500px] flex-col gap-3">
      <div className={`${card} p-3`}>
        <p className="mb-2 text-[10.5px] font-medium uppercase tracking-wide text-neutral-400">Before you send</p>
        <div className="rounded-xl border border-amber-300/80 bg-amber-50 p-3">
          <p className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-900">
            <AlertTriangle className="h-4 w-4 text-amber-600" /> This message may be unclear.
          </p>
          <p className="mt-1 text-[11.5px] leading-relaxed text-amber-950">
            The recipient may not know which task or deliverable is due or the exact deadline time.
          </p>
          <div className="mt-2 flex gap-2 border-t border-amber-200/70 pt-2">
            <span className="flex items-center gap-1 rounded-lg bg-amber-600 px-2.5 py-1 text-[11px] font-medium text-white">
              <Sparkles className="h-3 w-3" /> Improve message
            </span>
            <span className="rounded-lg border border-amber-300 px-2.5 py-1 text-[11px] font-medium text-amber-900">Send anyway</span>
          </div>
        </div>
        <div className="mt-2 rounded-full border border-black/[0.06] bg-neutral-50 px-3 py-1.5 text-[11.5px] text-neutral-800">
          Tomorrow is submission deadline.
        </div>
      </div>
      <div className={`${card} flex items-start gap-2 p-3`}>
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
        <p className="text-[11.5px] leading-relaxed text-neutral-700">
          After a message is sent, the same issue shows up for <strong>both</strong> people. The sender can clarify; the
          receiver can ask for clarification or confirm they understood.
        </p>
      </div>
    </div>
  )
}

export function RoutingVisual() {
  const nodes = [
    { y: 40, label: 'NVIDIA', note: 'cloud model' },
    { y: 130, label: 'Groq', note: 'cloud model' },
    { y: 220, label: 'Built-in engine', note: 'local fallback' },
  ]
  return (
    <div className="w-full max-w-[520px]">
      <svg viewBox="0 0 520 270" className="h-auto w-full" role="img" aria-label="Requests flow from the app to an adaptive router, which picks NVIDIA or Groq and can fall back to a built-in local engine.">
        <g fontFamily="inherit">
          <rect x="10" y="105" width="120" height="60" rx="14" fill="#13324a" stroke="#2f6d93" />
          <text x="70" y="131" textAnchor="middle" fill="#e6f6ff" fontSize="13" fontWeight="600">Your request</text>
          <text x="70" y="149" textAnchor="middle" fill="#8fb7cf" fontSize="10.5">alignment · drafts</text>

          <rect x="190" y="100" width="120" height="70" rx="16" fill="#0f3f4f" stroke="#34d3e8" />
          <text x="250" y="130" textAnchor="middle" fill="#e6fbff" fontSize="13" fontWeight="600">Adaptive router</text>
          <text x="250" y="149" textAnchor="middle" fill="#8fdbe8" fontSize="10.5">picks one, falls back once</text>
          <path d="M130 135 H190" stroke="#34d3e8" strokeWidth="2" className="lp-flow" fill="none" />

          {nodes.map((n) => (
            <g key={n.label}>
              <path d={`M310 135 C 350 135 350 ${n.y + 25} 380 ${n.y + 25}`} stroke="#5aa9e6" strokeWidth="1.6" fill="none" className="lp-flow" />
              <rect x="380" y={n.y} width="130" height="50" rx="12" fill="#112636" stroke="#2c5875" />
              <text x="445" y={n.y + 22} textAnchor="middle" fill="#e6f2ff" fontSize="12.5" fontWeight="600">{n.label}</text>
              <text x="445" y={n.y + 38} textAnchor="middle" fill="#8aa9c2" fontSize="9.5">{n.note}</text>
            </g>
          ))}
        </g>
      </svg>
    </div>
  )
}

export function VoiceVisual() {
  const bars = [6, 10, 16, 22, 14, 26, 18, 30, 20, 12, 24, 16, 28, 14, 10, 20, 26, 12, 18, 8, 14, 22, 10, 6]
  return (
    <div className={`${card} w-full max-w-[460px] p-4`}>
      <div className="flex items-center gap-3">
        <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-[#3D72B0] text-white">
          <Play className="ml-0.5 h-4 w-4 fill-current" />
        </span>
        <div className="flex h-10 flex-1 items-center gap-[3px]">
          {bars.map((h, i) => (
            <span
              key={i}
              className="lp-wavebar w-1 rounded-full bg-[#3D72B0]/70"
              style={{ height: `${h}px`, animationDelay: `${(i % 6) * 0.15}s` }}
            />
          ))}
        </div>
        <span className="text-[11px] tabular-nums text-neutral-500">0:24</span>
      </div>
      <div className="mt-3 rounded-xl bg-neutral-50 p-3">
        <p className="mb-1 text-[10.5px] font-semibold uppercase tracking-wide text-neutral-400">Transcript</p>
        <p className="text-[12.5px] leading-relaxed text-neutral-800">
          &ldquo;That sounds great. Let&apos;s move forward with the budget sheet, and I&apos;ll review it by ten.&rdquo;
        </p>
        <span className="mt-2 inline-flex items-center gap-1 rounded-md border border-black/[0.08] bg-white px-2 py-0.5 text-[10.5px] text-neutral-600">
          <Languages className="h-3 w-3" /> Translate
        </span>
      </div>
    </div>
  )
}

export function MeetVisual() {
  return (
    <div className="flex w-full max-w-[440px] flex-col gap-3">
      <div className={`${card} p-4`}>
        <div className="flex items-center gap-3">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-50 text-emerald-600">
            <Video className="h-5 w-5" />
          </span>
          <div>
            <p className="text-[13px] font-semibold text-neutral-900">Google Meet</p>
            <p className="text-[11px] text-neutral-500">Video call started from this chat</p>
          </div>
        </div>
        <div className="mt-3 flex items-center justify-between rounded-xl bg-neutral-50 px-3 py-2">
          <span className="font-mono text-[11px] text-neutral-600">meet.google.com/abc-defg-hij</span>
          <span className="rounded-lg bg-[#1a73e8] px-3 py-1 text-[11px] font-medium text-white">Join</span>
        </div>
      </div>
      <p className="px-1 text-[11px] leading-relaxed text-neutral-500">
        Example invitation. Starting a call asks you to connect your Google account first.
      </p>
    </div>
  )
}

export function RecommendationsVisual() {
  const recs = [
    { icon: Play, color: 'text-red-600 bg-red-50', title: 'Focus music for a late-night work session', src: 'YouTube' },
    { icon: Sparkles, color: 'text-emerald-600 bg-emerald-50', title: 'Calm acoustic playlist', src: 'Spotify' },
    { icon: Globe, color: 'text-sky-600 bg-sky-50', title: 'Weekend places to visit near Chennai', src: 'Web' },
  ]
  return (
    <div className="flex w-full max-w-[460px] flex-col gap-2.5">
      {recs.map((r) => (
        <div key={r.src} className={`${card} flex items-center gap-3 px-3.5 py-3`}>
          <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${r.color}`}>
            <r.icon className="h-4 w-4" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[12.5px] font-medium text-neutral-900">{r.title}</span>
            <span className="block text-[11px] text-neutral-500">{r.src}</span>
          </span>
          <span className="flex items-center gap-1 text-[11px] font-medium text-[#2f7fd8]">
            <Share2 className="h-3 w-3" /> Share
          </span>
        </div>
      ))}
      <p className="px-1 text-[11px] text-neutral-500">Illustrative examples. Results depend on which providers are configured.</p>
    </div>
  )
}

export function GroupVisual() {
  return (
    <div className={`${card} w-full max-w-[480px] overflow-hidden`}>
      <div className="flex items-center gap-2 border-b border-black/[0.06] px-4 py-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-full bg-neutral-200 text-neutral-600">
          <Users className="h-4 w-4" />
        </span>
        <div className="leading-tight">
          <p className="text-[13px] font-semibold text-neutral-900">Design Review</p>
          <p className="text-[11px] text-neutral-500">
            5 members · <span className="text-emerald-600">3 online</span>
          </p>
        </div>
      </div>
      <div className="flex flex-col gap-2 bg-[#f4f6f9] p-4">
        <p className="ml-1 text-[10.5px] text-neutral-500">@mira</p>
        <Bubble className="-mt-1.5">Let&apos;s lock the flow on Friday.</Bubble>
        <Bubble out>Friday works. Which version, v2 or v3?</Bubble>
        <div className="flex items-center gap-2 rounded-xl border border-sky-200 bg-white px-3 py-2 text-[11px] text-neutral-700">
          <MessageSquare className="h-3.5 w-3.5 shrink-0 text-sky-600" />
          Everyone in the group sees the same alignment check and its status.
        </div>
      </div>
    </div>
  )
}

export function PrivacyVisual() {
  const items = [
    { icon: Mail, t: 'Verified sign-up', d: 'One-time email codes confirm every new account.' },
    { icon: KeyRound, t: 'Hashed passwords', d: 'Stored with Argon2id, never in plain text.' },
    { icon: Lock, t: 'Encrypted Google tokens', d: 'Connected-account tokens are encrypted at rest.' },
    { icon: ToggleRight, t: 'AI on drafts is opt-in', d: 'Unsent drafts go to AI providers only if you allow it.' },
    { icon: Cpu, t: 'Gmail stays private', d: 'Only headers and a short snippet are read, and never sent to AI.' },
    { icon: ShieldCheck, t: 'Members only', d: 'Messages and files are checked against membership.' },
  ]
  return (
    <div className="grid w-full max-w-[520px] grid-cols-1 gap-2.5 sm:grid-cols-2">
      {items.map((it) => (
        <div key={it.t} className="rounded-2xl border border-white/10 bg-white/[0.06] p-3.5">
          <it.icon className="h-4 w-4 text-cyan-300" />
          <p className="mt-2 text-[12.5px] font-semibold text-white">{it.t}</p>
          <p className="mt-0.5 text-[11px] leading-relaxed text-cyan-50/70">{it.d}</p>
        </div>
      ))}
    </div>
  )
}
