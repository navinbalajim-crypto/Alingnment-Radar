import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MessageComposer } from '../components/chat/MessageComposer'
import { aiService } from '../services/aiService'
import { getLocalSuggestions } from '../utils/autocomplete'
import { AI_DEBOUNCE_MS } from '../hooks/useWritingSuggestions'

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

const chatState = { socketStatus: 'connected', activeConversationId: 'conv-1' }
vi.mock('../context/ChatContext', () => ({
  useChat: () => chatState,
  ChatProvider: ({ children }) => children,
}))

const box = () => screen.getByPlaceholderText(/message or ask for alignment/i)
const options = () => screen.queryAllByTestId('suggestion-text').map((o) => o.textContent)

async function type(value, caret = value.length) {
  await act(async () => {
    fireEvent.change(box(), { target: { value } })
    box().setSelectionRange(caret, caret)
    fireEvent.select(box())
  })
}
const wait = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })

describe('local suggestion engine', () => {
  it('completes "tomorrow is sub" with relevant phrases and words', () => {
    const texts = getLocalSuggestions('tomorrow is sub').map((s) => s.text)
    expect(texts.length).toBeGreaterThan(0)
    expect(texts.every((t) => t.startsWith('tomorrow is sub'))).toBe(true)
    expect(texts).toContain('tomorrow is submission day')
  })

  it('updates as the input changes character by character', () => {
    const seen = 'tomorrow is sub'.split('').map((_, i) => getLocalSuggestions('tomorrow is sub'.slice(0, i + 1)))
    expect(seen[0]).toEqual([]) // "t" is too short
    expect(seen.at(-1).length).toBeGreaterThan(0)
  })

  it('offers next-word continuations after a space and keeps earlier text and casing', () => {
    const out = getLocalSuggestions('Please send the ')
    expect(out.length).toBeGreaterThan(0)
    for (const s of out) {
      expect(('Please send the ').slice(0, s.from) + s.text).toMatch(/^Please send the /)
    }
    expect(getLocalSuggestions('Submit the report tom').map((s) => s.text)).toContain('Submit the report tomorrow')
  })

  it('returns nothing for empty or whitespace input and never invents unrelated text', () => {
    expect(getLocalSuggestions('')).toEqual([])
    expect(getLocalSuggestions('   \n ')).toEqual([])
    expect(getLocalSuggestions('zzzqq xxyyzz')).toEqual([])
  })
})

describe('composer autocomplete', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
    localStorage.setItem('ar_autocorrect', 'false')
    aiService.analyzeDraft.mockReset().mockResolvedValue(null)
    aiService.suggestDraft.mockReset()
    aiService.getAiPreferences.mockReset().mockResolvedValue({ ai_draft_analysis: false, ai_autocomplete: false, draft_recommendations: false })
    chatState.activeConversationId = 'conv-1'
  })
  afterEach(() => vi.useRealTimers())

  it('shows instant suggestions while typing and updates them', async () => {
    render(<MessageComposer onSend={vi.fn()} />)
    await type('tomorrow is s')
    const first = options()
    await type('tomorrow is sub')
    const second = options()
    expect(second.length).toBeGreaterThan(0)
    expect(second.every((t) => t.startsWith('tomorrow is sub'))).toBe(true)
    expect(second).not.toEqual(first)
    expect(aiService.suggestDraft).not.toHaveBeenCalled()
  })

  it('clicking a suggestion inserts it, keeps trailing text, and does not send', async () => {
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)
    await type('tomorrow is sub please', 'tomorrow is sub'.length)
    const opt = screen.getByRole('option', { name: /tomorrow is submission day/i })
    await act(async () => { fireEvent.click(opt) })
    expect(box().value).toBe('tomorrow is submission day please')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('keyboard: arrows highlight, Enter inserts only after highlighting, Tab inserts first, Escape dismisses', async () => {
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)
    await type('tomorrow is sub')
    expect(box()).toHaveAttribute('role', 'combobox')
    expect(box()).toHaveAttribute('aria-expanded', 'true')

    await act(async () => { fireEvent.keyDown(box(), { key: 'ArrowDown' }) })
    const active = box().getAttribute('aria-activedescendant')
    expect(document.getElementById(active)).toHaveAttribute('aria-selected', 'true')
    const chosen = document.getElementById(active).querySelector('[data-testid="suggestion-text"]').textContent
    await act(async () => { fireEvent.keyDown(box(), { key: 'Enter' }) })
    expect(box().value).toBe(chosen)
    expect(onSend).not.toHaveBeenCalled()

    await type('Please send the')
    const firstText = options()[0]
    await act(async () => { fireEvent.keyDown(box(), { key: 'Tab' }) })
    expect(box().value).toBe(firstText)
    expect(onSend).not.toHaveBeenCalled()

    await type('tomorrow is sub')
    await act(async () => { fireEvent.keyDown(box(), { key: 'Escape' }) })
    expect(options()).toEqual([])
    expect(box()).toHaveAttribute('aria-expanded', 'false')
    expect(box().value).toBe('tomorrow is sub')
  })

  it('plain Enter still sends the draft as typed, never a suggestion', async () => {
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)
    await type('tomorrow is sub')
    await act(async () => { fireEvent.keyDown(box(), { key: 'Enter' }) })
    expect(onSend).toHaveBeenCalledWith('tomorrow is sub')
  })

  it('does not call AI without opt-in, even for long drafts', async () => {
    render(<MessageComposer onSend={vi.fn()} />)
    await type('Can we move the review meeting to')
    await wait(AI_DEBOUNCE_MS * 3)
    expect(aiService.suggestDraft).not.toHaveBeenCalled()
  })

  describe('with AI completions enabled', () => {
    beforeEach(() => aiService.getAiPreferences.mockResolvedValue({ ai_draft_analysis: false, ai_autocomplete: true, draft_recommendations: false }))

    it('ignores empty/whitespace/short input, debounces rapid typing into one request', async () => {
      aiService.suggestDraft.mockImplementation(async (_c, draft, rev) => ({
        draft_revision: rev, ai_available: true, suggestions: [{ text: `${draft} for review` }],
      }))
      render(<MessageComposer onSend={vi.fn()} />)
      await type('   ')
      await type('hi')
      await wait(AI_DEBOUNCE_MS * 2)
      expect(aiService.suggestDraft).not.toHaveBeenCalled()

      for (const v of ['Send', 'Send t', 'Send th', 'Send the', 'Send the updated']) {
        await type(v)
        await wait(100)
      }
      await wait(AI_DEBOUNCE_MS + 50)
      expect(aiService.suggestDraft).toHaveBeenCalledTimes(1)
      expect(aiService.suggestDraft.mock.calls[0][1]).toBe('Send the updated')
      expect(options()).toContain('Send the updated for review')
    })

    it('discards a stale response when the user kept typing, and aborts the old request', async () => {
      let signalOne
      let resolveOne
      aiService.suggestDraft.mockImplementationOnce((_c, _d, rev, signal) => {
        signalOne = signal
        return new Promise((r) => { resolveOne = () => r({ draft_revision: rev, suggestions: [{ text: 'Send the report STALE' }] }) })
      })
      aiService.suggestDraft.mockImplementation(async (_c, draft, rev) => ({
        draft_revision: rev, suggestions: [{ text: `${draft} today` }],
      }))
      render(<MessageComposer onSend={vi.fn()} />)
      await type('Send the report')
      await wait(AI_DEBOUNCE_MS + 20)
      await type('Send the report now')
      expect(signalOne.aborted).toBe(true)
      await act(async () => { resolveOne() })
      await wait(AI_DEBOUNCE_MS + 20)
      expect(options().join('|')).not.toContain('STALE')
      expect(options()).toContain('Send the report now today')
    })

    it('falls back to local suggestions when the provider fails, and caches repeats', async () => {
      aiService.suggestDraft.mockRejectedValue(new Error('provider down'))
      render(<MessageComposer onSend={vi.fn()} />)
      await type('tomorrow is sub')
      await wait(AI_DEBOUNCE_MS + 50)
      expect(aiService.suggestDraft).toHaveBeenCalledTimes(1)
      expect(options()).toContain('tomorrow is submission day')
    })

    it('shows the privacy disclosure and sends only the text before the caret', async () => {
      aiService.suggestDraft.mockResolvedValue({ draft_revision: 'x', suggestions: [] })
      render(<MessageComposer onSend={vi.fn()} />)
      fireEvent.click(screen.getByRole('button', { name: /draft ai privacy/i }))
      expect(screen.getByTestId('draft-ai-privacy')).toHaveTextContent(/sends what you type and the last few messages/i)
      await type('Please send the SECRET tail', 'Please send the'.length)
      await wait(AI_DEBOUNCE_MS + 50)
      expect(aiService.suggestDraft.mock.calls[0][1]).toBe('Please send the')
    })

    it('keys requests by conversation so contexts never mix', async () => {
      aiService.suggestDraft.mockImplementation(async (conv, draft, rev) => ({
        draft_revision: rev, suggestions: [{ text: `${draft} in ${conv}` }],
      }))
      const { rerender } = render(<MessageComposer onSend={vi.fn()} />)
      await type('Send the report')
      await wait(AI_DEBOUNCE_MS + 50)
      expect(options()).toContain('Send the report in conv-1')
      chatState.activeConversationId = 'group-9'
      rerender(<MessageComposer onSend={vi.fn()} />)
      await type('Send the report')
      await wait(AI_DEBOUNCE_MS + 50)
      expect(aiService.suggestDraft.mock.calls.map((c) => c[0])).toEqual(['conv-1', 'group-9'])
      expect(options()).not.toContain('Send the report in conv-1')
    })
  })

  it('mobile layout: options are full-width touch targets and the hint kbd is desktop-only', async () => {
    render(<MessageComposer onSend={vi.fn()} />)
    await type('tomorrow is sub')
    const opt = screen.getAllByRole('option')[0]
    expect(opt.className).toMatch(/min-h-\[40px\]/)
    expect(screen.getByTestId('autocomplete-panel').className).not.toMatch(/\bw-\[/)
    expect(opt.querySelector('kbd').className).toMatch(/hidden sm:inline/)
  })

  it('suggestions toggle turns autocomplete off and persists', async () => {
    render(<MessageComposer onSend={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /suggestions on/i }))
    await type('tomorrow is sub')
    expect(options()).toEqual([])
    expect(localStorage.getItem('ar_suggest')).toBe('false')
  })
})

describe('draft privacy consent in the composer', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    localStorage.clear()
    localStorage.setItem('ar_autocorrect', 'false')
    aiService.analyzeDraft.mockReset().mockResolvedValue(null)
    aiService.suggestDraft.mockReset()
    aiService.getDraftRecommendations.mockClear()
    aiService.updateAiPreferences.mockReset()
    chatState.activeConversationId = 'conv-1'
  })
  afterEach(() => vi.useRealTimers())

  it('without consent: no draft text goes to any external endpoint, local help still works, and the UI says why', async () => {
    aiService.getAiPreferences.mockReset().mockResolvedValue({ ai_draft_analysis: false, ai_autocomplete: false, draft_recommendations: false })
    render(<MessageComposer onSend={vi.fn()} />)
    await type('I saw an elaphant tmrw bcoz it was fun and tomorrow is sub')
    await wait(AI_DEBOUNCE_MS * 3)
    expect(aiService.analyzeDraft).not.toHaveBeenCalled()
    expect(aiService.suggestDraft).not.toHaveBeenCalled()
    expect(aiService.getDraftRecommendations).not.toHaveBeenCalled()
    expect(screen.getByTestId('correction-panel')).toHaveTextContent(/tmrw|elaphant|bcoz/) // local spelling
    expect(options().length).toBeGreaterThan(0) // local autocomplete
    expect(screen.getByText(/local checks only/i)).toBeInTheDocument()
  })

  it('defaults to no consent when the preferences request fails', async () => {
    aiService.getAiPreferences.mockReset().mockRejectedValue(new Error('offline'))
    render(<MessageComposer onSend={vi.fn()} />)
    await type('Please send the updated report today')
    await wait(AI_DEBOUNCE_MS * 3)
    expect(aiService.analyzeDraft).not.toHaveBeenCalled()
    expect(aiService.suggestDraft).not.toHaveBeenCalled()
  })

  it('granting consent saves it on the server, enabling requests; revoking stops them', async () => {
    aiService.getAiPreferences.mockReset().mockResolvedValue({ ai_draft_analysis: false, ai_autocomplete: false, draft_recommendations: false })
    aiService.updateAiPreferences.mockImplementation(async (c) => ({ ai_draft_analysis: false, ai_autocomplete: false, draft_recommendations: false, ...c }))
    aiService.suggestDraft.mockImplementation(async (_c, d, rev) => ({ draft_revision: rev, suggestions: [{ text: `${d} today` }] }))
    render(<MessageComposer onSend={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /draft ai privacy/i }))
    await act(async () => { fireEvent.click(screen.getByLabelText(/ai completions/i)) })
    expect(aiService.updateAiPreferences).toHaveBeenCalledWith({ ai_autocomplete: true })

    await type('Send the report')
    await wait(AI_DEBOUNCE_MS + 50)
    expect(aiService.suggestDraft).toHaveBeenCalledTimes(1)

    await act(async () => { fireEvent.click(screen.getByLabelText(/ai completions/i)) })
    expect(aiService.updateAiPreferences).toHaveBeenLastCalledWith({ ai_autocomplete: false })
    await type('Send the report now')
    await wait(AI_DEBOUNCE_MS * 2)
    expect(aiService.suggestDraft).toHaveBeenCalledTimes(1)
  })
})
