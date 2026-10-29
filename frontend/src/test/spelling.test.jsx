import React from 'react'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeAll, beforeEach, afterEach } from 'vitest'
import { MessageComposer } from '../components/chat/MessageComposer'
import { aiService } from '../services/aiService'
import { loadSpellingAssets, classifyToken } from '../utils/spellChecker'
import { getWordCorrection, getWordCorrectionLegacy, analyzeDraftLocally } from '../utils/spellingEngine'

vi.mock('../services/aiService', () => ({
  aiService: {
    analyzeDraft: vi.fn(),
    suggestDraft: vi.fn(),
    getDraftRecommendations: vi.fn().mockResolvedValue({ recommendations: [] }),
    getAiPreferences: vi.fn(),
    updateAiPreferences: vi.fn(),
    shareRecommendation: vi.fn(),
  },
}))

const chatState = { socketStatus: 'connected', activeConversationId: 'conv-1', conversations: [] }
vi.mock('../context/ChatContext', () => ({
  useChat: () => chatState,
  ChatProvider: ({ children }) => children,
}))

const NO_AI = { ai_draft_analysis: false, ai_autocomplete: false, draft_recommendations: false }
const box = () => screen.getByPlaceholderText(/message or ask for alignment/i)
const readJson = (rel) => JSON.parse(fs.readFileSync(new URL(rel, import.meta.url), 'utf8'))

beforeAll(async () => {
  await loadSpellingAssets()
})

const fix = (word, prev = null) => getWordCorrection(word, { prev, atSentenceStart: !prev })?.corrected ?? word

describe('local spelling engine: clear typos', () => {
  it.each([
    ['yuo', 'you'],
    ['qick', 'quick'],
    ['teh', 'the'],
    ['becuase', 'because'],
    ['tomorow', 'tomorrow'],
    ['recieve', 'receive'],
  ])('%s -> %s', (typo, expected) => {
    expect(fix(typo, 'is')).toBe(expected)
  })

  it('fixes several typos in one sentence and keeps valid words (even a grammatically odd one)', () => {
    const { corrections, correctedText } = analyzeDraftLocally('the project is delay because of yuo so qick it fast')
    expect(correctedText).toBe('the project is delay because of you so quick it fast')
    expect(corrections.map((c) => c.original)).toEqual(['yuo', 'qick'])
  })

  it('never rewrites valid words, even rare ones or ones close to a more common word', () => {
    for (const w of ['delay', 'form', 'from', 'quick', 'their', 'there', 'unconfigured', 'rebuilds', 'const']) {
      expect(fix(w, 'the')).toBe(w)
    }
  })

  it('leaves proper nouns, usernames, URLs, emails, mentions, acronyms, code and numbers alone', () => {
    const ctx = { prev: 'ask', atSentenceStart: false, protectedWords: new Set(['navinstar', 'alise']) }
    for (const t of ['Anirudh', 'Chennai', 'navinstar', 'https://exmple.com/qick', 'bob@exmple.com', '@alise_t', 'NASA', 'getUserNmae', '`qick`', 'x2', 'v1.2.3']) {
      expect(classifyToken(t, ctx).status === 'auto' || classifyToken(t, ctx).status === 'suggest').toBe(false)
    }
    expect(analyzeDraftLocally('const status = await getStatus()').corrections).toEqual([])
  })

  it('preserves capitalisation and punctuation', () => {
    expect(getWordCorrection('Yuo,', { atSentenceStart: true }).corrected).toBe('You,')
    expect(getWordCorrection('(becuase)', { prev: 'of' }).corrected).toBe('(because)')
    expect(getWordCorrection('Teh', { atSentenceStart: true }).corrected).toBe('The')
    expect(classifyToken('QICK', { prev: 'so' }).status).toBe('skip') // short ALL-CAPS = acronym
  })

  it('ambiguous mistakes become suggestions, never automatic changes', () => {
    const r = classifyToken('feture', { prev: 'the' })
    expect(r.status).toBe('suggest')
    expect(r.alternatives.length).toBeGreaterThan(1)
    expect(getWordCorrection('feture', { prev: 'the' })).toBeNull()
  })

  it('slang and shorthand are suggestions only', () => {
    expect(getWordCorrection('wanna', { prev: 'i' })).toBeNull()
    expect(analyzeDraftLocally('i wanna go').corrections[0]).toMatchObject({ original: 'wanna', tier: 'suggest' })
  })
})

// data/test_pairs.json is built from third-party corpora that are not redistributed (docs/DATA_PROVENANCE.md);
// the word-pair check runs only where a developer has prepared that data locally.
const TEST_PAIRS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../../data/test_pairs.json')
const hasTestPairs = fs.existsSync(TEST_PAIRS)

describe('held-out evaluation regression', () => {
  const pairs = hasTestPairs ? JSON.parse(fs.readFileSync(TEST_PAIRS, 'utf8')).map((p) => [p.error.toLowerCase(), p.correction.toLowerCase()]) : []
  const chat = readJson('../../../data/chat_spelling_eval.json').filter((x) => x.split === 'test')
  const words = pairs.filter(([e]) => /^[a-z]{3,}$/.test(e))

  it.skipIf(!hasTestPairs)('improves on the previous engine on the held-out word pairs without hurting precision', { timeout: 120000 }, () => {
    let prevChanged = 0, prevOk = 0, changed = 0, ok = 0
    for (const [e, c] of words) {
      const p = getWordCorrectionLegacy(e)?.corrected
      if (p && p !== e) { prevChanged++; if (p === c) prevOk++ }
      const n = getWordCorrection(e, { atSentenceStart: true })?.corrected
      if (n && n !== e) { changed++; if (n === c) ok++ }
    }
    expect(ok / changed).toBeGreaterThan(0.9) // auto-correction precision
    expect(ok / words.length).toBeGreaterThan(0.25) // measured 0.32 vs 0.04 for the previous engine
    expect(ok).toBeGreaterThan(prevOk * 5)
    expect(prevOk / Math.max(prevChanged, 1)).toBeGreaterThan(0.9)
  })

  it('auto-corrects chat typos with no wrong fixes and never touches clean chat sentences', () => {
    const tok = (t) => t.split(/\s+/)
    let tp = 0, wrong = 0, falsePos = 0, typoTokens = 0
    for (const it of chat) {
      const a = tok(it.input)
      const b = tok(it.expected)
      a.forEach((t, i) => {
        // while typing only the left context exists
        const out = getWordCorrection(t, { prev: i ? a[i - 1] : null, atSentenceStart: i === 0 || /[.!?]$/.test(a[i - 1]) })?.corrected ?? t
        if (t === b[i]) { if (out !== t) falsePos++ } else { typoTokens++; if (out === b[i]) tp++; else if (out !== t) wrong++ }
      })
    }
    expect(falsePos).toBe(0)
    expect(wrong).toBe(0)
    expect(tp / typoTokens).toBeGreaterThan(0.55) // measured 0.67 (previous engine: 0.23)
  })
})

// Real typing appends to whatever the textarea currently holds (including any auto-correction).
async function typeChars(text) {
  for (const ch of text) {
    await act(async () => {
      fireEvent.change(box(), { target: { value: box().value + ch } })
    })
  }
}

describe('composer: correction while typing', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
    aiService.analyzeDraft.mockReset().mockResolvedValue(null)
    aiService.suggestDraft.mockReset()
    aiService.getDraftRecommendations.mockClear()
    aiService.getAiPreferences.mockReset().mockResolvedValue(NO_AI)
    chatState.activeConversationId = 'conv-1'
  })
  afterEach(() => vi.useRealTimers())

  const ready = async (onSend = vi.fn()) => {
    render(<MessageComposer onSend={onSend} />)
    await act(async () => { await loadSpellingAssets(); await vi.advanceTimersByTimeAsync(50) })
    return onSend
  }

  it('corrects clear typos character by character, keeps typing normal, and never sends', async () => {
    const onSend = await ready()
    await typeChars('the project is delay because of yuo so qick it fast')
    expect(box().value).toBe('the project is delay because of you so quick it fast')
    expect(box().selectionStart).toBe(box().value.length)
    // continued typing after a correction
    await typeChars(' now')
    expect(box().value).toBe('the project is delay because of you so quick it fast now')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('keeps the caret right after the corrected word when editing mid-text', async () => {
    await ready()
    await act(async () => { fireEvent.change(box(), { target: { value: 'send yuo the file' } }) }) // typo already present, no boundary typed yet
    // user places the caret after "yuo" and types a space
    await act(async () => {
      fireEvent.change(box(), { target: { value: 'send yuo  the file', selectionStart: 9, selectionEnd: 9 } })
      await vi.advanceTimersByTimeAsync(50)
    })
    expect(box().value).toBe('send you  the file')
    expect(box().selectionStart).toBe(9)
  })

  it('does not auto-correct while Auto-correct is off, but still offers the correction as an optional suggestion', async () => {
    localStorage.setItem('ar_autocorrect', 'false')
    await ready()
    await typeChars('thanks to yuo ')
    expect(box().value).toBe('thanks to yuo ')
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    expect(screen.getByTestId('correction-panel')).toHaveTextContent(/yuo/)
    expect(screen.getByTestId('correction-panel')).toHaveTextContent(/you/)
  })

  it('autocomplete and spelling correction work together', async () => {
    await ready()
    await typeChars('tomorow is sub')
    expect(box().value).toBe('tomorrow is sub') // typo fixed at its word boundary, caret/typing undisturbed
    const texts = screen.getAllByTestId('suggestion-text').map((e) => e.textContent)
    expect(texts.length).toBeGreaterThan(0)
    expect(texts.every((t) => t.startsWith('tomorrow is sub'))).toBe(true)
    await act(async () => { fireEvent.click(screen.getAllByRole('option')[0]) })
    expect(box().value.startsWith('tomorrow is sub')).toBe(true)
    expect(box().value.length).toBeGreaterThan('tomorrow is sub'.length)
  })

  it('does not call any external provider while consent is disabled', async () => {
    await ready()
    await typeChars('the project is delay because of yuo so qick it fast ')
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(aiService.analyzeDraft).not.toHaveBeenCalled()
    expect(aiService.suggestDraft).not.toHaveBeenCalled()
    expect(aiService.getDraftRecommendations).not.toHaveBeenCalled()
  })
})

describe('composer: external AI writing check (consent enabled)', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
    localStorage.setItem('ar_autocorrect', 'false')
    aiService.analyzeDraft.mockReset()
    aiService.getAiPreferences.mockReset().mockResolvedValue({ ...NO_AI, ai_draft_analysis: true })
    chatState.activeConversationId = 'conv-1'
  })
  afterEach(() => vi.useRealTimers())

  const flush = () => act(async () => { await vi.advanceTimersByTimeAsync(900) })

  it('falls back to local corrections when the provider fails', async () => {
    aiService.analyzeDraft.mockRejectedValue(new Error('groq and nvidia down'))
    render(<MessageComposer onSend={vi.fn()} />)
    await act(async () => { await loadSpellingAssets(); await vi.advanceTimersByTimeAsync(50) })
    await act(async () => { fireEvent.change(box(), { target: { value: 'thanks to yuo and teh team' } }) })
    await flush()
    expect(aiService.analyzeDraft).toHaveBeenCalled()
    expect(screen.getByTestId('correction-panel')).toHaveTextContent(/yuo/)
  })

  it('ignores a slow response for old text once the user has typed more', async () => {
    let resolveOld
    aiService.analyzeDraft.mockImplementationOnce((_c, _d, rev) => new Promise((r) => {
      resolveOld = () => r({ draft_revision: rev, ai_available: true, corrections: [{ original: 'OLDTYPO', corrected: 'STALE', reason: 'x', confidence: 0.9 }], completions: [] })
    }))
    aiService.analyzeDraft.mockImplementation(async (_c, _d, rev) => ({ draft_revision: rev, ai_available: true, corrections: [], completions: [] }))
    render(<MessageComposer onSend={vi.fn()} />)
    await act(async () => { await loadSpellingAssets(); await vi.advanceTimersByTimeAsync(50) })
    await act(async () => { fireEvent.change(box(), { target: { value: 'first draft OLDTYPO here' } }) })
    await flush()
    await act(async () => { fireEvent.change(box(), { target: { value: 'a completely different draft now' } }) })
    await act(async () => { resolveOld() })
    await flush()
    expect(screen.queryByText(/STALE/)).toBeNull()
  })

  it('does not resend an identical draft', async () => {
    aiService.analyzeDraft.mockImplementation(async (_c, _d, rev) => ({ draft_revision: rev, ai_available: true, corrections: [], completions: [] }))
    render(<MessageComposer onSend={vi.fn()} />)
    await act(async () => { await loadSpellingAssets(); await vi.advanceTimersByTimeAsync(50) })
    await act(async () => { fireEvent.change(box(), { target: { value: 'please review the document today' } }) })
    await flush()
    await act(async () => { fireEvent.change(box(), { target: { value: 'please review the document today' } }) })
    await flush()
    expect(aiService.analyzeDraft).toHaveBeenCalledTimes(1)
  })
})

describe('composer: alternatives for ambiguous words', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
    localStorage.setItem('ar_autocorrect', 'false')
    aiService.analyzeDraft.mockReset().mockResolvedValue(null)
    aiService.getAiPreferences.mockReset().mockResolvedValue(NO_AI)
  })
  afterEach(() => vi.useRealTimers())

  it('lets the user pick an alternative; only that word changes', async () => {
    render(<MessageComposer onSend={vi.fn()} />)
    await act(async () => { await loadSpellingAssets(); await vi.advanceTimersByTimeAsync(50) })
    await act(async () => { fireEvent.change(box(), { target: { value: 'the feture is ready' } }) })
    await act(async () => { await vi.advanceTimersByTimeAsync(800) })
    const alt = screen.getAllByRole('button', { name: /use .* instead of feture/i })[0]
    const chosen = alt.textContent
    await act(async () => { fireEvent.click(alt) })
    expect(box().value).toBe(`the ${chosen} is ready`)
  })
})
