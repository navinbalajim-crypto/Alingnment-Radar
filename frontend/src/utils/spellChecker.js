/**
 * Local-first spelling checker (no network). Shared design with backend/app/services/spell_checker.py:
 * the same assets (data/spelling_assets.json) and the same scoring, so both engines agree.
 *
 *   candidates = dictionary words within Damerau-OSA distance <= 2 (<= 1 for short words)
 *   score      = ln(frequency) - lambda * weightedEditCost + mu * bigramContext
 *   status     = 'ok'      the word is a valid dictionary word (never changed)
 *                'skip'    protected: URL, email, @mention, code, acronym, proper noun, usernames...
 *                'auto'    one clear winner -> safe to apply automatically
 *                'suggest' plausible candidates but not clear -> offered, never applied silently
 */

let assets = null
let vocab = null // Map word -> index
let byLength = null // length -> array of indices
let letterCounts = null // flat Uint8Array: 26 letter counts per word (cheap pre-filter)
const queryCounts = new Uint8Array(26)

export const DEFAULT_PARAMS = {
  lambda: 3.0,
  mu: 0.25,
  bigramFloor: 10.0,
  autoMargin: 2.0,
  maxAutoCost: 1.6,
  minAutoLogFreq: 9.0,
}

export function setSpellingAssets(data) {
  assets = data
  vocab = new Map()
  byLength = new Map()
  letterCounts = new Uint8Array(data.words.length * 26)
  data.words.forEach((w, i) => {
    for (let k = 0; k < w.length; k++) letterCounts[i * 26 + (w.charCodeAt(k) - 97)]++
    vocab.set(w, i)
    const list = byLength.get(w.length) || []
    list.push(i)
    byLength.set(w.length, list)
  })
}

export async function loadSpellingAssets() {
  if (assets) return assets
  const mod = await import('../data/spelling_assets.json')
  setSpellingAssets(mod.default || mod)
  return assets
}

export const spellingAssetsLoaded = () => assets !== null

const params = () => ({ ...DEFAULT_PARAMS, ...(assets?.params || {}) })

// context breaks ties between plausible edits; it must not override the edit evidence
export const BIGRAM_CAP = 3
const DUP_FACTOR = 0.6
const PRED_FACTOR = 0.6

const ROWS = ['qwertyuiop', 'asdfghjkl', 'zxcvbnm']
const KEY = {}
ROWS.forEach((row, r) => [...row].forEach((c, i) => { KEY[c] = [r, i + 0.5 * r] }))
const adjacent = (a, b) => {
  const p = KEY[a]
  const q = KEY[b]
  return !!p && !!q && a !== b && Math.abs(p[0] - q[0]) <= 1 && Math.abs(p[1] - q[1]) <= 1.01
}

/** Weighted Damerau (optimal string alignment) cost, with a hard cap on the *number* of edits. */
export function weightedEditCost(a, b, maxEdits = 2) {
  const m = assets.errorModel
  const c = m.cost
  const fm = m.firstLetterMultiplier
  const n = a.length
  const k = b.length
  if (Math.abs(n - k) > maxEdits) return null
  const INF = 1e9
  // d[i][j] = [cost, edits]
  const d = Array.from({ length: n + 1 }, () => Array.from({ length: k + 1 }, () => [INF, 99]))
  d[0][0] = [0, 0]
  const better = (x, y) => (x[0] < y[0] ? x : y)
  const add = (x, cost) => [x[0] + cost, x[1] + 1]
  for (let i = 0; i <= n; i++) {
    for (let j = 0; j <= k; j++) {
      const cur = d[i][j]
      if (cur[0] >= INF) continue
      if (i < n) {
        // extra typed letter; a doubled letter ('usefull') is a very common slip
        const dup = (i > 0 && a[i] === a[i - 1]) || (i + 1 < n && a[i] === a[i + 1])
        d[i + 1][j] = better(d[i + 1][j], add(cur, c.ins * (i === 0 ? fm : 1) * (dup ? DUP_FACTOR : 1)))
      }
      if (j < k) {
        // omitted letter; cheaper when English makes it predictable from the previous letter ('u' after 'q')
        const pred = j > 0 ? assets.letterNext[(b.charCodeAt(j - 1) - 97) * 26 + (b.charCodeAt(j) - 97)] : 0
        d[i][j + 1] = better(d[i][j + 1], add(cur, c.del * (j === 0 ? fm : 1) * (1 - PRED_FACTOR * pred)))
      }
      if (i < n && j < k) {
        if (a[i] === b[j]) d[i + 1][j + 1] = better(d[i + 1][j + 1], [cur[0], cur[1]])
        else d[i + 1][j + 1] = better(d[i + 1][j + 1], add(cur, (adjacent(a[i], b[j]) ? c.subAdj : c.subFar) * (i === 0 ? fm : 1)))
      }
      if (i + 1 < n && j + 1 < k && a[i] === b[j + 1] && a[i + 1] === b[j] && a[i] !== a[i + 1]) {
        d[i + 2][j + 2] = better(d[i + 2][j + 2], add(cur, c.trans * (i === 0 ? fm : 1)))
      }
    }
  }
  const res = d[n][k]
  return res[1] <= maxEdits ? res[0] : null
}

const maxEditsFor = (len) => (len <= 4 ? 1 : 2)

function bigramBonus(prev, word, next, p) {
  let bonus = 0
  if (prev) {
    const lb = assets.bigrams[`${prev} ${word}`]
    if (lb !== undefined) bonus += Math.min(BIGRAM_CAP, Math.max(0, lb - p.bigramFloor))
  }
  if (next) {
    const lb = assets.bigrams[`${word} ${next}`]
    if (lb !== undefined) bonus += Math.min(BIGRAM_CAP, Math.max(0, lb - p.bigramFloor))
  }
  return bonus
}

/** Every dictionary word within the edit budget, with its weighted edit cost (context-free, cacheable). */
export function allCandidates(word) {
  if (!assets) return []
  const maxEdits = maxEditsFor(word.length)
  const out = []
  // A substitution changes two letter counts, an insertion/deletion one, a transposition none.
  const budget = 2 * maxEdits
  queryCounts.fill(0)
  for (let k = 0; k < word.length; k++) queryCounts[word.charCodeAt(k) - 97]++
  for (let len = word.length - maxEdits; len <= word.length + maxEdits; len++) {
    const list = byLength.get(len)
    if (!list) continue
    for (const idx of list) {
      let diff = 0
      const base = idx * 26
      for (let k = 0; k < 26 && diff <= budget; k++) {
        const d = queryCounts[k] - letterCounts[base + k]
        diff += d < 0 ? -d : d
      }
      if (diff > budget) continue
      const cand = assets.words[idx]
      const cost = weightedEditCost(word, cand, maxEdits)
      if (cost !== null) out.push({ word: cand, cost, logFreq: assets.logFreq[idx] })
    }
  }
  return out
}

/** Score and sort candidates for a given context and parameter set. */
export function scoreCandidates(cands, prev, next, p = params()) {
  return cands
    .map((c) => ({ ...c, score: c.logFreq - p.lambda * c.cost + p.mu * bigramBonus(prev, c.word, next, p) }))
    .sort((x, y) => y.score - x.score)
}

/** Ranked correction candidates for an unknown lowercase word. */
export function rankCandidates(word, prev = null, next = null, limit = 5) {
  return scoreCandidates(allCandidates(word), prev, next).slice(0, limit)
}

/** Is the top candidate a clear winner (safe to auto-apply)? */
export function isClear(ranked, p = params()) {
  const best = ranked[0]
  const second = ranked[1]
  const margin = second ? best.score - second.score : Infinity
  return margin >= p.autoMargin && best.cost <= p.maxAutoCost && best.logFreq >= p.minAutoLogFreq
}

const PREFIXES = ['un', 'non', 'pre', 'dis', 'mis', 'anti', 'inter', 'over', 'under', 'multi', 'semi']
const SUFFIXES = ['s', 'es', 'ed', 'd', 'ing', 'ly', 'er', 'ers', 'est', 'ness', 'ment', 'ments', 'able', 'ible', 'ful', 'less', 'ity', 'ion', 'ions', 'al', 'ish']

/** A valid affix on a known base word ('unconfigured', 'rebuilds') is not a typo, even if the list lacks it. */
export function isDerivedWord(w) {
  if (w.length < 6) return false
  for (const p of PREFIXES) {
    if (w.startsWith(p) && w.length - p.length >= 4 && vocab.has(w.slice(p.length))) return true
  }
  for (const x of SUFFIXES) {
    if (!w.endsWith(x)) continue
    const base = w.slice(0, w.length - x.length)
    if (base.length < 4) continue
    if (vocab.has(base) || vocab.has(base + 'e')) return true
    if (base[base.length - 1] === base[base.length - 2] && vocab.has(base.slice(0, -1))) return true
  }
  return false
}

/** Code-like text (statements, tags, backticks) is never spell-checked. */
export const looksLikeCode = (text) => /[{};]|=>|\w\(|\s=\s|`|<\/?[a-z]+>/.test(text)

const SENTENCE_END = /[.!?]["')\]]*$/

/**
 * Classify one token.
 * @param {string} raw        token as typed (may carry surrounding punctuation)
 * @param {object} ctx        { prev, next, atSentenceStart, protectedWords:Set<string> } (prev/next: raw neighbours)
 * @returns {{status:string, corrected?:string, alternatives?:string[], confidence?:number}}
 */
export function classifyToken(raw, ctx = {}) {
  if (!assets || !raw) return { status: 'skip' }
  const m = raw.match(/^([^A-Za-z0-9'’]*)([A-Za-z'’]+)([^A-Za-z0-9'’]*)$/)
  if (!m) return { status: 'skip' } // digits, @mentions, urls, emails, paths, code
  const [, prefix, core, suffix] = m
  // @mentions, #tags, $vars, `code`, <tags>: not prose
  if (/[@#$`<]/.test(prefix) || /[`>]/.test(suffix)) return { status: 'skip' }
  if (/['’]/.test(core)) return { status: 'skip' } // contractions are handled by the typo map
  if (core.length < 3) return { status: 'skip' }
  const lower = core.toLowerCase()

  if (ctx.protectedWords && ctx.protectedWords.has(lower)) return { status: 'skip' }
  // acronyms / shouting / camelCase / code-like identifiers
  if (core === core.toUpperCase() && core.length <= 6) return { status: 'skip' }
  if (/[a-z][A-Z]/.test(core)) return { status: 'skip' }
  // capitalised mid-sentence word: a name, not a typo
  if (core[0] !== core[0].toLowerCase() && core.slice(1) === core.slice(1).toLowerCase() && !ctx.atSentenceStart) {
    return { status: 'skip' }
  }
  if (ctx.codeLike) return { status: 'skip' }
  if (vocab.has(lower) || isDerivedWord(lower)) return { status: 'ok' }

  const prev = ctx.prev ? ctx.prev.toLowerCase().replace(/[^a-z]/g, '') : null
  const next = ctx.next ? ctx.next.toLowerCase().replace(/[^a-z]/g, '') : null
  const ranked = rankCandidates(lower, prev || null, next || null, 3)
  if (ranked.length === 0) return { status: 'skip' } // nothing plausible: leave the user's text alone

  const p = params()
  const best = ranked[0]
  const apply = (w) => `${prefix}${matchCase(core, w)}${suffix}`
  const alternatives = ranked.map((r) => apply(r.word))
  const clear = isClear(ranked, p)
  return {
    status: clear ? 'auto' : 'suggest',
    corrected: apply(best.word),
    alternatives,
    confidence: clear ? 0.97 : 0.6,
  }
}

export function matchCase(original, target) {
  if (original === original.toUpperCase() && original.length > 1) return target.toUpperCase()
  if (original[0] !== original[0].toLowerCase()) return target.charAt(0).toUpperCase() + target.slice(1)
  return target
}

/**
 * Check a whole draft. Returns per-token results plus suggested replacements.
 * Tokens are split on whitespace so punctuation and spacing are preserved exactly.
 */
export function checkText(text, options = {}) {
  const codeLike = looksLikeCode(text)
  const tokens = text.split(/(\s+)/)
  const words = tokens.map((t, i) => ({ t, i })).filter((x) => x.t && !/^\s+$/.test(x.t))
  const results = []
  words.forEach((w, n) => {
    const prevTok = n > 0 ? words[n - 1].t : null
    const nextTok = n + 1 < words.length ? words[n + 1].t : null
    const atSentenceStart = n === 0 || SENTENCE_END.test(prevTok)
    const r = classifyToken(w.t, {
      prev: prevTok,
      next: nextTok,
      atSentenceStart,
      protectedWords: options.protectedWords,
      codeLike,
    })
    if (r.status === 'auto' || r.status === 'suggest') results.push({ tokenIndex: w.i, original: w.t, ...r })
  })
  return { tokens, results }
}
