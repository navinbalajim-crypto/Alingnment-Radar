/**
 * Generates backend/tests/fixtures/spelling_parity.json from the JS engine so the Python port can be checked.
 * Uses only project-authored text (data/chat_spelling_eval.json and the literals below), so the fixture can be
 * redistributed with the repository.
 */
import fs from 'node:fs'
import { setSpellingAssets, classifyToken } from '../frontend/src/utils/spellChecker.js'

const assets = JSON.parse(fs.readFileSync('data/spelling_assets.json', 'utf8'))
setSpellingAssets(assets)
const vocab = new Set(assets.words)
const chat = JSON.parse(fs.readFileSync('data/chat_spelling_eval.json', 'utf8'))
const cases = []
const add = (raw, prev = null, next = null, atSentenceStart = false) => {
  const r = classifyToken(raw, { prev, next, atSentenceStart })
  cases.push({ raw, prev, next, atSentenceStart, expected: { status: r.status, corrected: r.corrected ?? null, alternatives: r.alternatives ?? null } })
}
// every misspelled chat word on its own, with no context
const isolated = new Set(chat.flatMap((it) => it.input.split(' ')).filter((t) => /^[a-z]+$/.test(t) && !vocab.has(t)))
isolated.forEach((t) => add(t, null, null, true))
for (const it of chat) {
  const a = it.input.split(' ')
  a.forEach((t, i) => add(t, i > 0 ? a[i - 1] : null, i + 1 < a.length ? a[i + 1] : null, i === 0 || /[.!?]$/.test(a[i - 1])))
}
for (const [raw, s] of [['Teh', true], ['Yuo,', true], ['Anirudh', false], ['https://exmple.com/a', false], ['bob@exmple.com', false],
  ['@alise_t', false], ['NASA', false], ['getUserNmae', false], ['`qick`', false], ['recieve.', false], ['(becuase)', false], ['QICK', false], ['x2', false]]) add(raw, 'the', 'it', s)
fs.writeFileSync('backend/tests/fixtures/spelling_parity.json', JSON.stringify(cases))
console.log(cases.length, 'parity cases')
