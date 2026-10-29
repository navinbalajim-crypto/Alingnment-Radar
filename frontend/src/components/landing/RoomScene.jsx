// Illustrated room based on the reference storyboard: dark teal walls, round night
// window, cork board, string lights, neon sign, red armchair, candle and teapot, and a
// desk monitor. Drawn on a 1600 x 900 stage; MONITOR is the screen area (stage px)
// where the live HTML chat is layered on top.
export const STAGE = { w: 1600, h: 900 }
export const MONITOR = { x: 1010, y: 286, w: 452, h: 276 }
// Phone screen held in the girl's raised hand (stage px, rotated about its centre).
export const PHONE = { x: 764, y: 486, w: 32, h: 58, rot: -10 }

const BULBS = Array.from({ length: 22 }, (_, i) => {
  const t = i / 21
  const x = 60 + t * 1480
  const y = 64 + Math.sin(t * Math.PI * 3) * 22 + 26 * Math.sin(t * Math.PI)
  return { x, y, delay: (i % 5) * 0.6 }
})

const STARS = [
  [170, 250], [205, 300], [262, 240], [300, 330], [190, 380], [238, 410], [318, 280], [150, 320], [280, 395],
]

const NOTES = [
  { x: 398, y: 190, w: 54, h: 46, c: '#f3e6c4', r: -4 },
  { x: 468, y: 202, w: 48, h: 40, c: '#f7c9c2', r: 3 },
  { x: 532, y: 186, w: 58, h: 52, c: '#cfe7e4', r: -2 },
  { x: 410, y: 262, w: 60, h: 44, c: '#f7c9c2', r: 2 },
  { x: 488, y: 266, w: 46, h: 54, c: '#f3e6c4', r: -3 },
  { x: 552, y: 270, w: 52, h: 42, c: '#f3e6c4', r: 4 },
]

export function RoomScene() {
  return (
    <svg
      viewBox={`0 0 ${STAGE.w} ${STAGE.h}`}
      className="absolute inset-0 h-full w-full overflow-visible"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id="lp-wall" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#0f2427" />
          <stop offset="0.7" stopColor="#14302f" />
          <stop offset="1" stopColor="#0c1b1c" />
        </linearGradient>
        <linearGradient id="lp-floor" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#24170f" />
          <stop offset="1" stopColor="#120b07" />
        </linearGradient>
        <radialGradient id="lp-warm" cx="0.42" cy="0.62" r="0.45">
          <stop offset="0" stopColor="#ffb661" stopOpacity="0.32" />
          <stop offset="0.5" stopColor="#ff9a4a" stopOpacity="0.1" />
          <stop offset="1" stopColor="#ff9a4a" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="lp-screenglow" cx="0.5" cy="0.5" r="0.5">
          <stop offset="0" stopColor="#bfe6ff" stopOpacity="0.32" />
          <stop offset="1" stopColor="#bfe6ff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="lp-sky" cx="0.6" cy="0.3" r="0.8">
          <stop offset="0" stopColor="#2b5a86" />
          <stop offset="1" stopColor="#0b1a33" />
        </radialGradient>
        <linearGradient id="lp-velvet" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#7a2620" />
          <stop offset="1" stopColor="#3e110f" />
        </linearGradient>
        <linearGradient id="lp-jacket" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#e2a43a" />
          <stop offset="1" stopColor="#a8701c" />
        </linearGradient>
        <linearGradient id="lp-jeans" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#2a3446" />
          <stop offset="1" stopColor="#1a2130" />
        </linearGradient>
        <radialGradient id="lp-hair" cx="0.45" cy="0.4" r="0.6">
          <stop offset="0" stopColor="#a4502a" />
          <stop offset="1" stopColor="#5e2914" />
        </radialGradient>
        <linearGradient id="lp-skin" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#f1c39e" />
          <stop offset="1" stopColor="#d79a72" />
        </linearGradient>
        <filter id="lp-glow" x="-100%" y="-100%" width="300%" height="300%">
          <feGaussianBlur stdDeviation="5" result="b" />
          <feMerge>
            <feMergeNode in="b" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="lp-blur" x="-50%" y="-50%" width="200%" height="200%">
          <feGaussianBlur stdDeviation="14" />
        </filter>
        <clipPath id="lp-window-clip">
          <circle cx="240" cy="320" r="140" />
        </clipPath>
      </defs>

      {/* Wall and floor (extended past the stage so the camera never sees an edge) */}
      <rect x="-1600" y="-600" width="4800" height="1320" fill="#11292a" />
      <rect x="-1600" width="4800" height="900" fill="url(#lp-wall)" />
      <rect x="-1600" y="720" width="4800" height="780" fill="url(#lp-floor)" />
      <rect x="-1600" y="716" width="4800" height="8" fill="#0a1112" opacity="0.8" />
      <ellipse cx="760" cy="800" rx="520" ry="70" fill="#3a2a2a" opacity="0.55" />
      <ellipse cx="760" cy="800" rx="460" ry="56" fill="none" stroke="#6b4b3a" strokeWidth="3" opacity="0.4" />

      {/* Round window with night sky */}
      <g>
        <circle cx="240" cy="320" r="140" fill="url(#lp-sky)" />
        <g clipPath="url(#lp-window-clip)">
          {STARS.map(([x, y], i) => (
            <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 2.2 : 1.4} fill="#f2f7ff" className="lp-bulb" style={{ animationDelay: `${i * 0.4}s` }} />
          ))}
          <circle cx="318" cy="246" r="22" fill="#fdf3d6" opacity="0.9" filter="url(#lp-glow)" />
        </g>
        <circle cx="240" cy="320" r="140" fill="none" stroke="#6e4a2b" strokeWidth="18" />
        <circle cx="240" cy="320" r="148" fill="none" stroke="#3d2816" strokeWidth="4" />
        <line x1="240" y1="180" x2="240" y2="460" stroke="#6e4a2b" strokeWidth="9" />
        <line x1="100" y1="320" x2="380" y2="320" stroke="#6e4a2b" strokeWidth="9" />
        <circle cx="240" cy="320" r="70" fill="none" stroke="#6e4a2b" strokeWidth="6" />
      </g>

      {/* Cork board */}
      <rect x="380" y="170" width="250" height="186" rx="6" fill="#8b5a33" stroke="#5a381d" strokeWidth="8" />
      {NOTES.map((n, i) => (
        <g key={i} transform={`rotate(${n.r} ${n.x + n.w / 2} ${n.y + n.h / 2})`}>
          <rect x={n.x} y={n.y} width={n.w} height={n.h} fill={n.c} opacity="0.92" />
          <rect x={n.x + 8} y={n.y + 12} width={n.w - 18} height="3" fill="#7b6a58" opacity="0.4" />
          <rect x={n.x + 8} y={n.y + 20} width={n.w - 24} height="3" fill="#7b6a58" opacity="0.4" />
          <circle cx={n.x + n.w / 2} cy={n.y + 4} r="3.5" fill="#d94b3b" />
        </g>
      ))}
      <path d="M425 196 L495 270 L561 192" fill="none" stroke="#d94b3b" strokeWidth="1.5" opacity="0.7" />

      {/* String lights */}
      <path
        d={`M${BULBS.map((b) => `${b.x} ${b.y}`).join(' L')}`}
        fill="none"
        stroke="#2c2620"
        strokeWidth="2"
      />
      {BULBS.map((b, i) => (
        <circle
          key={i}
          cx={b.x}
          cy={b.y + 7}
          r="5"
          fill="#ffd79a"
          filter="url(#lp-glow)"
          className="lp-bulb"
          style={{ animationDelay: `${b.delay}s` }}
        />
      ))}

      {/* Neon sign */}
      <text
        x="770"
        y="200"
        fill="#ffb3c4"
        filter="url(#lp-glow)"
        fontSize="58"
        fontStyle="italic"
        fontFamily="'Segoe Script','Brush Script MT','Snell Roundhand',cursive"
        textAnchor="middle"
      >
        let&apos;s talk
      </text>

      {/* Warm candle light pooling around the chair */}
      <rect width="1600" height="900" fill="url(#lp-warm)" />

      {/* Plant by the window */}
      <g>
        <rect x="88" y="660" width="86" height="64" rx="10" fill="#c77a4a" />
        {[
          'M131 662 C 90 600 60 560 66 500 C 110 520 130 580 131 662',
          'M131 662 C 150 590 190 540 240 530 C 230 590 180 630 131 662',
          'M131 662 C 120 590 130 520 160 470 C 180 530 160 600 131 662',
        ].map((d, i) => (
          <path key={i} d={d} fill={i === 1 ? '#2f6b46' : '#27593a'} className="lp-leaf" style={{ animationDelay: `${i * 1.3}s` }} />
        ))}
      </g>

      {/* Low table with teapot and candle */}
      <rect x="330" y="664" width="190" height="14" rx="5" fill="#4a2f1c" />
      <rect x="348" y="678" width="10" height="46" fill="#3a2414" />
      <rect x="492" y="678" width="10" height="46" fill="#3a2414" />
      <g>
        <ellipse cx="392" cy="644" rx="34" ry="24" fill="#f3efe6" />
        <path d="M358 640 q-22 -6 -26 -20" fill="none" stroke="#f3efe6" strokeWidth="7" strokeLinecap="round" />
        <path d="M426 632 q16 2 16 16 q0 12 -14 14" fill="none" stroke="#e6dfd2" strokeWidth="6" />
        <ellipse cx="392" cy="620" rx="16" ry="5" fill="#e0d8ca" />
        <circle cx="392" cy="613" r="5" fill="#e0d8ca" />
      </g>
      <g>
        <rect x="468" y="626" width="20" height="38" rx="3" fill="#f5ead2" />
        <ellipse cx="478" cy="612" rx="6" ry="13" fill="#ffcf73" className="lp-flame" filter="url(#lp-glow)" />
        <circle cx="478" cy="640" r="60" fill="#ffb661" opacity="0.14" filter="url(#lp-blur)" />
      </g>

      {/* Desk and monitor */}
      <rect x="960" y="610" width="560" height="18" rx="4" fill="#3f2a1b" />
      <rect x="990" y="628" width="14" height="96" fill="#2e1f14" />
      <rect x="1476" y="628" width="14" height="96" fill="#2e1f14" />
      <rect x="1206" y="566" width="60" height="30" fill="#1b2127" />
      <rect x="1166" y="594" width="140" height="16" rx="6" fill="#20262d" />
      <rect
        x={MONITOR.x - 14}
        y={MONITOR.y - 14}
        width={MONITOR.w + 28}
        height={MONITOR.h + 28}
        rx="16"
        fill="#161b21"
        stroke="#2a323b"
        strokeWidth="2"
      />
      <ellipse
        cx={MONITOR.x + MONITOR.w / 2}
        cy={MONITOR.y + MONITOR.h / 2}
        rx={MONITOR.w * 0.95}
        ry={MONITOR.h * 1.1}
        fill="url(#lp-screenglow)"
      />
      {/* Desk props: mug and a small lamp */}
      <rect x="1500" y="574" width="0" height="0" />
      <g>
        <rect x="1010" y="580" width="26" height="30" rx="4" fill="#d9e7ee" />
        <path d="M1036 588 q10 0 10 8 q0 8 -10 8" fill="none" stroke="#d9e7ee" strokeWidth="4" />
      </g>

      {/* Armchair */}
      <g>
        <rect x="560" y="440" width="96" height="300" rx="40" fill="url(#lp-velvet)" />
        <rect x="560" y="600" width="330" height="120" rx="34" fill="url(#lp-velvet)" />
        <rect x="830" y="560" width="70" height="150" rx="30" fill="#5c1a17" />
        <rect x="576" y="720" width="18" height="40" rx="4" fill="#2a1410" />
        <rect x="856" y="720" width="18" height="40" rx="4" fill="#2a1410" />
      </g>

      {/* The girl */}
      <g>
        {/* Back leg */}
        <path d="M700 612 L786 600 L792 612 L786 740 L762 740 L764 630 L704 640 Z" fill="#1d2433" />
        <path d="M758 736 h38 q12 0 12 12 v10 h-54 z" fill="#2a1d17" />

        {/* Torso (breathing) */}
        <g className="lp-breathe">
          <path d="M650 618 Q640 520 676 482 Q706 458 744 470 Q778 486 772 560 L770 620 Z" fill="url(#lp-jacket)" />
          <path d="M704 474 Q720 520 712 600 L690 600 Q694 530 690 480 Z" fill="#f3efe6" />
          <path d="M688 482 L702 520 L694 600" fill="none" stroke="#9a6418" strokeWidth="3" opacity="0.6" />
        </g>

        {/* Front leg (crossed over) */}
        <path d="M680 600 Q690 588 720 588 L836 596 Q852 600 848 616 L840 742 L812 742 L816 628 L708 640 Q684 640 680 620 Z" fill="url(#lp-jeans)" />
        <path d="M808 738 h44 q14 0 14 14 v10 h-62 z" fill="#2f2019" />

        {/* Arm resting on armrest */}
        <path d="M744 488 Q790 520 786 572 L770 578 Q764 534 732 512 Z" fill="#c78a2c" />
        {/* Arm raised, holding the phone up to read it */}
        <path d="M676 500 Q668 566 742 560 L752 540 Q700 546 698 506 Z" fill="#d49530" />
        {/* Phone body (its screen content is a live HTML layer, see PHONE) */}
        <g transform={`rotate(${PHONE.rot} ${PHONE.x + PHONE.w / 2} ${PHONE.y + PHONE.h / 2})`}>
          <rect x={PHONE.x - 3} y={PHONE.y - 5} width={PHONE.w + 6} height={PHONE.h + 10} rx="7" fill="#11161d" stroke="#2c3540" strokeWidth="1" />
        </g>
        <circle cx={PHONE.x + PHONE.w / 2} cy={PHONE.y + PHONE.h / 2} r="46" fill="#9fd8ff" opacity="0.16" filter="url(#lp-blur)" />
        {/* Hand wrapped around the phone */}
        <ellipse cx="756" cy="542" rx="11" ry="9" fill="url(#lp-skin)" />
        <path d="M762 534 q8 -2 10 4" fill="none" stroke="#d79a72" strokeWidth="5" strokeLinecap="round" />

        {/* Neck and head */}
        <rect x="708" y="440" width="22" height="36" rx="8" fill="#d89c74" />
        <g className="lp-head">
          {/* Hair behind */}
          <g fill="url(#lp-hair)">
            {[
              [690, 384, 34], [672, 414, 30], [676, 448, 26], [700, 372, 30], [728, 366, 28],
              [756, 378, 26], [664, 440, 24], [690, 470, 22], [706, 440, 26],
            ].map(([cx, cy, r], i) => (
              <circle key={i} cx={cx} cy={cy} r={r} />
            ))}
          </g>
          {/* Face (3/4 view, turned toward the monitor) */}
          <path d="M716 386 Q760 378 768 414 Q772 446 744 458 Q720 462 712 440 Z" fill="url(#lp-skin)" />
          <ellipse cx="738" cy="428" rx="5" ry="3" fill="#f2a08a" opacity="0.55" />
          <g className="lp-eye">
            <ellipse cx="752" cy="414" rx="3.4" ry="4" fill="#2a1a14" />
          </g>
          <path className="lp-brow" d="M744 404 q8 -4 15 0" fill="none" stroke="#5e2914" strokeWidth="3" strokeLinecap="round" />
          <path d="M768 420 q4 6 0 10" fill="none" stroke="#c98563" strokeWidth="2" />
          <path d="M748 442 q6 4 12 0" fill="none" stroke="#b5584a" strokeWidth="2.6" strokeLinecap="round" />
          {/* Fringe curls over the forehead */}
          <g fill="url(#lp-hair)">
            {[[724, 384, 16], [742, 378, 14], [758, 386, 11], [712, 400, 13]].map(([cx, cy, r], i) => (
              <circle key={i} cx={cx} cy={cy} r={r} />
            ))}
          </g>
        </g>
      </g>
    </svg>
  )
}
