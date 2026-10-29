/**
 * Reproducible evaluation (and parameter tuning) of the local spelling engine.
 *
 *   node scripts/evaluate_spelling.mjs --tune    tune on the project-authored chat DEV split only, write params
 *   node scripts/evaluate_spelling.mjs           held-out evaluation: chat TEST split (+ test_pairs.json if present)
 *   node scripts/evaluate_spelling.mjs --json    machine-readable output
 *
 * Compares the previous engine (curated map only: getWordCorrectionLegacy) with the improved engine
 * (map + dictionary/edit-cost/context) on exactly the same held-out data.
 *
 * data/test_pairs.json comes from third-party corpora that are not redistributed with this repository
 * (see docs/DATA_PROVENANCE.md). When it exists locally it is reported for comparison only; it is never used
 * for tuning.
 */
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import {
  setSpellingAssets, classifyToken, DEFAULT_PARAMS,
} from '../frontend/src/utils/spellChecker.js'
import { getWordCorrection, getWordCorrectionLegacy } from '../frontend/src/utils/spellingEngine.js'

const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)))
const read = (p) => JSON.parse(fs.readFileSync(path.join(ROOT, p), 'utf8'))
const ASSET_PATHS = ['data/spelling_assets.json', 'frontend/src/data/spelling_assets.json']
const args = new Set(process.argv.slice(2))

const assets = read(ASSET_PATHS[0])
setSpellingAssets(assets)
const vocab = new Set(assets.words)

const TEST_PAIRS = 'data/test_pairs.json'
const test = fs.existsSync(path.join(ROOT, TEST_PAIRS))
  ? read(TEST_PAIRS).map((p) => ({ e: p.error.toLowerCase(), c: p.correction.toLowerCase() }))
  : null
const chat = read('data/chat_spelling_eval.json')
const CHAT_DEV_PARAMS_SOURCE = 'tuned on data/chat_spelling_eval.json (dev split, project-authored)'

// Valid-but-unusual lowercase words people type in chat (tools, names, food, slang), authored for this project.
// None is in the dictionary; an auto-correction of any of them is a false correction.
const RARE_CLEAN_WORDS = [
  'kubectl', 'nginx', 'pytest', 'vitest', 'webpack', 'dockerfile', 'jsonb', 'linter', 'monorepo', 'tailwind',
  'figma', 'jira', 'slackbot', 'chennai', 'bengaluru', 'coimbatore', 'anirudh', 'biryani', 'dosa', 'idli',
  'lgtm', 'brb', 'ngl', 'imo', 'tbd', 'wfh', 'standups', 'onboarded', 'dashboards', 'refactor',
]

const isWord = (w) => /^[a-z]+$/.test(w) && w.length >= 3

// ---------- token-level scoring on chat sets ----------
const tokensOf = (t) => t.split(/\s+/).filter(Boolean)

function chatScore(items, correctToken) {
  let tp = 0, wrong = 0, fn = 0, fp = 0, tn = 0, exact = 0
  for (const it of items) {
    const a = tokensOf(it.input)
    const b = tokensOf(it.expected)
    const out = a.map((tok, i) => correctToken(tok, a, i))
    out.forEach((o, i) => {
      if (a[i] === b[i]) (o !== a[i] ? fp++ : tn++)
      else if (o === b[i]) tp++
      else if (o === a[i]) fn++
      else wrong++
    })
    if (out.join(' ') === it.expected) exact++
  }
  const precision = tp / Math.max(tp + wrong + fp, 1)
  const recall = tp / Math.max(tp + wrong + fn, 1)
  return { tokensWithTypos: tp + wrong + fn, tp, wrong, fn, falseCorrections: fp, cleanTokens: tp + 0 + tn + fp - tp, precision, recall, exact, sentences: items.length }
}

const ctxFor = (a, i) => ({
  prev: i > 0 ? a[i - 1] : null,
  next: i + 1 < a.length ? a[i + 1] : null,
  atSentenceStart: i === 0 || /[.!?]$/.test(a[i - 1]),
})
const legacyToken = (tok) => getWordCorrectionLegacy(tok)?.corrected ?? tok
// While typing, a word is auto-corrected the moment its trailing space/punctuation is typed: only LEFT context exists.
const autoToken = (tok, a, i) => getWordCorrection(tok, { ...ctxFor(a, i), next: null })?.corrected ?? tok
const suggestToken = (tok, a, i) => {
  const r = getWordCorrection(tok, { ...ctxFor(a, i), next: null })
  if (r) return r.corrected
  const c = classifyToken(tok, ctxFor(a, i))
  return c.status === 'suggest' ? c.corrected : tok
}

// ---------- tuning ----------
if (args.has('--tune')) {
  // Only project-authored data is used: the chat DEV split and RARE_CLEAN_WORDS. The chat TEST split and any
  // third-party pairs are never read while tuning.
  const devChat = chat.filter((x) => x.split === 'dev')
  const devTypos = devChat.filter((x) => x.kind === 'typo')
  const devClean = devChat.filter((x) => x.kind === 'clean')
  const rareClean = RARE_CLEAN_WORDS.filter((w) => !vocab.has(w))
  const countFalseAuto = (p) => {
    setSpellingAssets({ ...assets, params: p })
    return rareClean.filter((w) => classifyToken(w, { prev: 'the' }).status === 'auto').length
  }
  const defaultFalseAuto = countFalseAuto({ ...DEFAULT_PARAMS })

  const rows = []
  for (const lambda of [1.5, 2, 3, 4, 5]) {
    for (const autoMargin of [1, 1.5, 2, 3, 4, 5]) {
      for (const maxAutoCost of [1.2, 1.6, 2.2]) {
        const p = { ...DEFAULT_PARAMS, ...assets.params, lambda, autoMargin, maxAutoCost, mu: DEFAULT_PARAMS.mu }
        const falseAuto = countFalseAuto(p)
        const t = chatScore(devTypos, autoToken)
        const c = chatScore(devClean, autoToken)
        rows.push({ lambda, autoMargin, maxAutoCost, devTp: t.tp, devWrong: t.wrong, devFalse: c.falseCorrections, falseAuto })
      }
    }
  }
  if (args.has('--table')) {
    for (const r of [...rows].sort((a, b) => b.devTp - a.devTp).slice(0, 40)) {
      console.log(`lambda=${r.lambda} margin=${r.autoMargin} maxCost=${r.maxAutoCost} devTp=${r.devTp} devWrong=${r.devWrong} devFalse=${r.devFalse} falseAuto=${r.falseAuto}`)
    }
  }
  // Precision-first selection. A config is acceptable only if on the chat DEV split it makes no wrong and no false
  // auto-corrections and it auto-corrects no more rare clean words than the defaults do. Among acceptable configs,
  // maximise chat-DEV correct fixes; ties go to the more conservative config (larger margin, then lower max cost,
  // then lambda closest to the default 3). If none qualifies, keep the defaults.
  console.log(`rare clean words auto-corrected with default params: ${defaultFalseAuto}/${rareClean.length}`)
  const acceptable = rows.filter((r) => r.devWrong === 0 && r.devFalse === 0 && r.falseAuto <= defaultFalseAuto)
  const conservative = (a, b) => b.devTp - a.devTp || b.autoMargin - a.autoMargin || a.maxAutoCost - b.maxAutoCost
    || Math.abs(a.lambda - 3) - Math.abs(b.lambda - 3)
  const pick = acceptable.length ? [...acceptable].sort(conservative)[0] : { ...DEFAULT_PARAMS }
  console.log(`acceptable configs: ${acceptable.length}/${rows.length}`)
  const chosen = { ...DEFAULT_PARAMS, ...assets.params, lambda: pick.lambda, autoMargin: pick.autoMargin, maxAutoCost: pick.maxAutoCost }

  // context weight mu tuned on chat DEV (token-level)
  let bestMu = { mu: 0, f: -1 }
  for (const mu of [0, 0.1, 0.25, 0.4, 0.6]) {
    setSpellingAssets({ ...assets, params: { ...chosen, mu } })
    const typos = devChat.filter((x) => x.kind === 'typo')
    const cleans = devChat.filter((x) => x.kind === 'clean')
    const s = chatScore(typos, autoToken)
    const c = chatScore(cleans, autoToken)
    const f = s.tp - 2 * s.wrong - 3 * c.falseCorrections
    console.error(`mu=${mu}: tp=${s.tp} wrong=${s.wrong} cleanFalse=${c.falseCorrections}`)
    // ties keep the value closest to the documented default
    if (f > bestMu.f || (f === bestMu.f && Math.abs(mu - DEFAULT_PARAMS.mu) < Math.abs(bestMu.mu - DEFAULT_PARAMS.mu))) bestMu = { mu, f }
  }
  chosen.mu = bestMu.mu
  console.log('chosen (chat dev only):', JSON.stringify(chosen), JSON.stringify(pick))
  for (const rel of ASSET_PATHS) {
    const file = path.join(ROOT, rel)
    const a = JSON.parse(fs.readFileSync(file, 'utf8'))
    a.params = chosen
    a.sources = { ...a.sources, params: CHAT_DEV_PARAMS_SOURCE }
    fs.writeFileSync(file, JSON.stringify(a))
  }
  console.log('params written to', ASSET_PATHS.join(', '))
  process.exit(0)
}

// ---------- held-out evaluation ----------
const t0 = performance.now()
function isolated(fn) {
  let changed = 0, correct = 0, validWord = 0, skipped = 0
  for (const p of test) {
    if (!isWord(p.e)) { skipped++; continue }
    const out = fn(p.e)
    if (vocab.has(p.e) && out === p.e) validWord++
    if (out !== p.e) { changed++; if (out.toLowerCase() === p.c) correct++ }
  }
  const n = test.length - skipped
  return { n, changed, correct, precision: correct / Math.max(changed, 1), recall: correct / n, errorIsValidDictionaryWord: validWord }
}
const iso = test
  ? {
      previous: isolated((w) => legacyToken(w)),
      improvedAuto: isolated((w) => autoToken(w, [w], 0)),
      improvedWithSuggestions: isolated((w) => suggestToken(w, [w], 0)),
    }
  : `skipped: ${TEST_PAIRS} not present (third-party data, not redistributed)`
const chatTest = chat.filter((x) => x.split === 'test')
const chatTypos = chatTest.filter((x) => x.kind === 'typo')
const chatClean = chatTest.filter((x) => x.kind === 'clean')
const report = {
  assets: { words: assets.words.length, bigrams: Object.keys(assets.bigrams).length, errorModel: assets.errorModel, params: assets.params },
  isolatedWords_testPairs: iso,
  chatTypoSentences: {
    previous: chatScore(chatTypos, legacyToken),
    improvedAuto: chatScore(chatTypos, autoToken),
    improvedWithSuggestions: chatScore(chatTypos, suggestToken),
  },
  chatCleanSentences_falseCorrections: {
    previous: chatScore(chatClean, legacyToken).falseCorrections,
    improvedAuto: chatScore(chatClean, autoToken).falseCorrections,
    improvedWithSuggestions: chatScore(chatClean, suggestToken).falseCorrections,
    cleanSentences: chatClean.length,
  },
}
// falsely corrected clean tokens (for transparency)
report.falseCorrectionExamples = []
for (const it of chatClean) {
  const a = tokensOf(it.input)
  a.forEach((tok, i) => { const o = suggestToken(tok, a, i); if (o !== tok) report.falseCorrectionExamples.push(`${tok} -> ${o}`) })
}
// latency
const words = [...new Set(chatTypos.flatMap((it) => tokensOf(it.input)).filter((w) => isWord(w) && !vocab.has(w)))]
const l0 = performance.now()
for (const w of words) autoToken(w, [w], 0)
report.latencyMsPerUnknownWord = (performance.now() - l0) / words.length
const s0 = performance.now()
for (let i = 0; i < 200; i++) for (const it of chatTypos.slice(0, 10)) tokensOf(it.input).forEach((t, j, a) => autoToken(t, a, j))
report.latencyMsPerChatToken = (performance.now() - s0) / (200 * chatTypos.slice(0, 10).reduce((n, it) => n + tokensOf(it.input).length, 0))
report.exampleSentence = (() => {
  const text = 'the project is delay because of yuo so qick it fast'
  const a = tokensOf(text)
  return a.map((t, i) => autoToken(t, a, i)).join(' ')
})()

if (args.has('--json')) console.log(JSON.stringify(report))
else console.log(JSON.stringify(report, null, 2))
console.error(`done in ${((performance.now() - t0) / 1000).toFixed(1)}s`)
