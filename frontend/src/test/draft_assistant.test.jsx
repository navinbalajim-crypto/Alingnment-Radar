import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MessageComposer } from '../components/chat/MessageComposer'
import { aiService } from '../services/aiService'

vi.mock('../services/aiService', () => ({
  aiService: {
    analyzeDraft: vi.fn(),
    getDraftRecommendations: vi.fn().mockResolvedValue({ recommendations: [] }),
    getAiPreferences: vi.fn().mockResolvedValue({ ai_draft_analysis: true, ai_autocomplete: false, draft_recommendations: true }),
    updateAiPreferences: vi.fn(),
    shareRecommendation: vi.fn(),
  },
}))

const chatState = { socketStatus: 'connected', activeConversationId: 'conv-1' }
vi.mock('../context/ChatContext', () => ({
  useChat: () => chatState,
  ChatProvider: ({ children }) => children,
}))

const textarea = () => screen.getByPlaceholderText(/message or ask for alignment/i)

async function type(value) {
  await act(async () => {
    fireEvent.change(textarea(), { target: { value } })
  })
}

async function passDebounce() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(800)
  })
}

const echoRevision = (body) => (_conv, _draft, revision) => Promise.resolve({ draft_revision: revision, ai_available: true, ...body })

describe('Draft assistant in the composer', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    aiService.analyzeDraft.mockReset()
    chatState.activeConversationId = 'conv-1'
    localStorage.setItem('ar_autocorrect', 'false')
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows correction suggestions after the debounce, with request matching the backend schema', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: 'I will send it tomorrow because I am busy.',
      corrections: [
        { original: 'tmrw', corrected: 'tomorrow', reason: 'Abbreviation', confidence: 0.95 },
        { original: 'bcoz', corrected: 'because', reason: 'Abbreviation', confidence: 0.95 },
      ],
      completions: [],
      tone: 'professional',
    }))
    render(<MessageComposer onSend={vi.fn()} />)
    await type('I will send it tmrw bcoz I am busy.')
    await passDebounce()

    expect(aiService.analyzeDraft).toHaveBeenCalledTimes(1)
    const [convId, draft, revision] = aiService.analyzeDraft.mock.calls[0]
    expect(convId).toBe('conv-1')
    expect(draft).toBe('I will send it tmrw bcoz I am busy.')
    expect(revision).toMatch(/^rev-\d+$/)

    const panel = screen.getByTestId('correction-panel')
    expect(panel).toHaveTextContent('tmrw')
    expect(panel).toHaveTextContent('tomorrow')
    expect(panel).toHaveTextContent('2 writing suggestions')
  })

  it('accepting one correction edits only that word and never sends; others stay', async () => {
    const onSend = vi.fn()
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: 'This is information about the elephant.',
      corrections: [
        { original: 'infoooorm', corrected: 'information', reason: 'Spelling' },
        { original: 'elaphant', corrected: 'elephant', reason: 'Spelling' },
      ],
      completions: [],
    }))
    render(<MessageComposer onSend={onSend} />)
    await type('This is infoooorm about the elaphant.')
    await passDebounce()

    await act(async () => {
      fireEvent.click(screen.getByLabelText('Accept correction elaphant to elephant'))
    })
    expect(textarea().value).toBe('This is infoooorm about the elephant.')
    expect(screen.getByTestId('correction-panel')).toHaveTextContent('infoooorm')
    expect(onSend).not.toHaveBeenCalled()

    await act(async () => {
      fireEvent.click(screen.getByText('Accept all'))
    })
    expect(textarea().value).toBe('This is information about the elephant.')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('dismissing a correction hides it without changing the draft', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: 'see you tomorrow',
      corrections: [{ original: 'tmrw', corrected: 'tomorrow', reason: 'Abbreviation' }],
      completions: [],
    }))
    render(<MessageComposer onSend={vi.fn()} />)
    await type('see you tmrw')
    await passDebounce()
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Dismiss correction tmrw'))
    })
    expect(screen.queryByTestId('correction-panel')).toBeNull()
    expect(textarea().value).toBe('see you tmrw')
  })

  it('ignores a response for an older draft when the user kept typing', async () => {
    let resolveFirst
    aiService.analyzeDraft.mockImplementationOnce((_c, _d, revision) => new Promise((r) => {
      resolveFirst = () => r({
        draft_revision: revision,
        corrected_text: 'I will send it tomorrow',
        corrections: [{ original: 'tmrw', corrected: 'tomorrow', reason: 'x' }],
        completions: [],
      })
    }))
    aiService.analyzeDraft.mockImplementation(() => new Promise(() => {}))

    render(<MessageComposer onSend={vi.fn()} />)
    await type('I will send it tmrw')
    await passDebounce()
    await type('I will send it tmrw and the slides')
    await act(async () => {
      resolveFirst()
    })
    expect(screen.queryByTestId('correction-panel')).toBeNull()
    expect(textarea().value).toBe('I will send it tmrw and the slides')
  })

  it('Tab inserts the first completion only when the caret is at the end, and never sends', async () => {
    const onSend = vi.fn()
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrections: [],
      completions: [
        { text: 'Can we move the review meeting to Friday?' },
        { text: 'Can we move the review meeting to next week?' },
        { text: 'A third one that must not render' },
      ],
    }))
    render(<MessageComposer onSend={onSend} />)
    await type('Can we move the review meeting to')
    await passDebounce()

    expect(screen.getAllByRole('option')).toHaveLength(2)

    const el = textarea()
    el.setSelectionRange(0, 0)
    const notHandled = fireEvent.keyDown(el, { key: 'Tab' })
    expect(notHandled).toBe(true)
    expect(el.value).toBe('Can we move the review meeting to')

    el.setSelectionRange(el.value.length, el.value.length)
    await act(async () => {
      fireEvent.keyDown(el, { key: 'Tab' })
    })
    expect(el.value).toBe('Can we move the review meeting to Friday?')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('does not call the API for very short drafts', async () => {
    render(<MessageComposer onSend={vi.fn()} />)
    await type('hi')
    await passDebounce()
    expect(aiService.analyzeDraft).not.toHaveBeenCalled()
  })

  it('shows an unavailable status when the backend reports AI is unavailable', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({ ai_available: false, corrections: [], completions: [] }))
    render(<MessageComposer onSend={vi.fn()} />)
    await type('Some draft that needs checking')
    await passDebounce()
    expect(screen.getByText('Writing assistant unavailable')).toBeInTheDocument()
    expect(screen.queryByLabelText('Checking writing')).toBeNull()
  })

  it('network failure keeps the draft, ends loading, and sending still works', async () => {
    aiService.analyzeDraft.mockRejectedValue(new Error('Network error'))
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)
    await type('This message should still send fine')
    await passDebounce()

    expect(textarea().value).toBe('This message should still send fine')
    expect(screen.queryByLabelText('Checking writing')).toBeNull()
    expect(screen.getByText('Writing assistant unavailable')).toBeInTheDocument()

    await act(async () => {
      fireEvent.keyDown(textarea(), { key: 'Enter' })
    })
    expect(onSend).toHaveBeenCalledWith('This message should still send fine')
    expect(textarea().value).toBe('')
  })

  it('switching conversations clears the draft and suggestions', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: 'see you tomorrow',
      corrections: [{ original: 'tmrw', corrected: 'tomorrow', reason: 'x' }],
      completions: [],
    }))
    const { rerender } = render(<MessageComposer onSend={vi.fn()} />)
    await type('see you tmrw')
    await passDebounce()
    expect(screen.getByTestId('correction-panel')).toBeInTheDocument()

    chatState.activeConversationId = 'conv-2'
    await act(async () => {
      rerender(<MessageComposer onSend={vi.fn()} />)
    })
    expect(textarea().value).toBe('')
    expect(screen.queryByTestId('correction-panel')).toBeNull()
  })

  it('renders contextual draft recommendations dock when recommendations are returned for music draft', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: null,
      corrections: [],
      completions: [],
    }))
    aiService.getDraftRecommendations.mockResolvedValue({
      draft_revision: 'rev-1',
      has_intent: true,
      category: 'music',
      query: 'Anirudh',
      recommendations: [
        {
          id: 'rec-1',
          source: 'spotify',
          title: 'Hukum - Anirudh Ravichander',
          url: 'https://open.spotify.com/track/12345',
          category: 'music',
          extra_data: { artist: 'Anirudh Ravichander' },
          is_shared_in_chat: false,
        },
      ],
    })

    render(<MessageComposer onSend={vi.fn()} />)
    await type('I like Anirudh songs')
    await passDebounce()

    expect(screen.getByTestId('draft-recommendations-dock')).toBeInTheDocument()
    expect(screen.getByText('Contextual Suggestions')).toBeInTheDocument()
    expect(screen.getByText('"Anirudh"')).toBeInTheDocument()
    expect(screen.getByText('Hukum - Anirudh Ravichander')).toBeInTheDocument()
    expect(screen.getByText('Share in Chat')).toBeInTheDocument()
  })

  it('has auto-correct enabled by default and automatically corrects typos on space', async () => {
    localStorage.removeItem('ar_autocorrect')
    render(<MessageComposer onSend={vi.fn()} />)
    expect(screen.getByText('Auto-correct On')).toBeInTheDocument()

    // Type 'misic ' with trailing space
    await type('I like misic ')
    expect(textarea().value).toBe('I like music ')
  })

  it('allows toggling auto-correct off and keeping manual suggestions', async () => {
    localStorage.removeItem('ar_autocorrect')
    render(<MessageComposer onSend={vi.fn()} />)
    const toggleBtn = screen.getByLabelText(/Toggle auto-correction/i)
    fireEvent.click(toggleBtn)
    expect(screen.getByText('Auto-correct Off')).toBeInTheDocument()

    // When off, space does not auto-replace
    await type('I like misic ')
    expect(textarea().value).toBe('I like misic ')
  })

  it('optimizes phrasing for tomorrow is submission', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: 'The submission is due tomorrow.',
      corrections: [
        { original: 'tomorrow is submission', corrected: 'The submission is due tomorrow.', reason: 'The deadline is unclear.' },
      ],
      completions: [],
    }))
    render(<MessageComposer onSend={vi.fn()} />)
    await type('tomorrow is submission')
    await passDebounce()
    expect(screen.getByText('The submission is due tomorrow.')).toBeInTheDocument()
    expect(screen.getByText(/The deadline is unclear/i)).toBeInTheDocument()
  })

  it('blocks whitespace-only messages and displays inline warning', async () => {
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)
    
    // Type only whitespace and press Enter
    await type('     ')
    fireEvent.keyDown(textarea(), { key: 'Enter', code: 'Enter' })

    expect(onSend).not.toHaveBeenCalled()
    expect(screen.getByTestId('empty-message-warning')).toBeInTheDocument()
    expect(screen.getByText(/Your message is empty. Add a message or a clarification before sending/i)).toBeInTheDocument()
  })

  it('allows sending legitimate short messages like OK or yes', async () => {
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)
    
    await type('OK')
    fireEvent.keyDown(textarea(), { key: 'Enter', code: 'Enter' })

    expect(onSend).toHaveBeenCalledWith('OK')
    expect(screen.queryByTestId('empty-message-warning')).not.toBeInTheDocument()
  })

  it('detects pre-send ambiguity for unclear messages like "Tomorrow is deadline." and displays inline suggestions', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: true,
      ambiguity_details: 'The recipient may not know which task is due or the exact deadline.',
      suggested_actions: ['Add the task or deliverable.', 'Add the deadline time if known.'],
      improved_draft: 'Tomorrow at 10 AM IST, we need to submit the implementation.',
    }))

    render(<MessageComposer onSend={vi.fn()} />)
    await type('Tomorrow is deadline.')
    await passDebounce()

    expect(screen.getByTestId('pre-send-ambiguity-panel')).toBeInTheDocument()
    expect(screen.getByText('This message may be unclear.')).toBeInTheDocument()
    expect(screen.getByTestId('ambiguity-details')).toHaveTextContent(
      'The recipient may not know which task is due or the exact deadline.'
    )
    expect(screen.getByText('Add the task or deliverable.')).toBeInTheDocument()
    expect(screen.getByText('Add the deadline time if known.')).toBeInTheDocument()
    expect(screen.getByTestId('improve-message-btn')).toBeInTheDocument()
    expect(screen.getByTestId('send-anyway-btn')).toBeInTheDocument()
  })

  it('sender clicking "Improve message" updates the draft for editing and does NOT send automatically', async () => {
    const onSend = vi.fn()
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: true,
      ambiguity_details: 'The recipient may not know which task is due or the exact deadline.',
      suggested_actions: ['Add the task or deliverable.'],
      improved_draft: 'Tomorrow at 10 AM IST, we need to submit the implementation.',
    }))

    render(<MessageComposer onSend={onSend} />)
    await type('Tomorrow is deadline.')
    await passDebounce()

    await act(async () => {
      fireEvent.click(screen.getByTestId('improve-message-btn'))
    })

    expect(textarea().value).toBe('Tomorrow at 10 AM IST, we need to submit the implementation.')
    expect(onSend).not.toHaveBeenCalled()
  })

  it('first click on "Improve message" produces a changed draft for a vague deadline with no task and no time (regression)', async () => {
    // AI reports no ambiguity (or is unavailable), so the composer falls back to the
    // local heuristic engine -- this is the path that previously returned the draft unchanged.
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: false,
    }))

    render(<MessageComposer onSend={vi.fn()} />)
    const original = 'Tomorrow is submission deadline.'
    await type(original)
    await passDebounce()

    expect(screen.getByTestId('improve-message-btn')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByTestId('improve-message-btn'))
    })

    expect(textarea().value).not.toBe(original)
    expect(textarea().value.length).toBeGreaterThan(0)
  })

  it('sender clicking "Send anyway" sends the original draft as-is', async () => {
    const onSend = vi.fn()
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: true,
      ambiguity_details: 'Missing task and deadline time.',
      suggested_actions: ['Specify task.'],
      improved_draft: 'Tomorrow at 10 AM, submit report.',
    }))

    render(<MessageComposer onSend={onSend} />)
    await type('Tomorrow is deadline.')
    await passDebounce()

    await act(async () => {
      fireEvent.click(screen.getByTestId('send-anyway-btn'))
    })

    expect(onSend).toHaveBeenCalledWith('Tomorrow is deadline.')
    expect(textarea().value).toBe('')
    expect(screen.queryByTestId('pre-send-ambiguity-panel')).toBeNull()
  })

  it('sender can dismiss the ambiguity warning and it does not re-appear for unchanged draft', async () => {
    aiService.analyzeDraft.mockImplementation(echoRevision({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: true,
      ambiguity_details: 'Missing task details.',
      suggested_actions: ['Clarify missing details.'],
    }))

    render(<MessageComposer onSend={vi.fn()} />)
    await type('Tomorrow is deadline.')
    await passDebounce()

    expect(screen.getByTestId('pre-send-ambiguity-panel')).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByLabelText('Dismiss ambiguity warning'))
    })

    expect(screen.queryByTestId('pre-send-ambiguity-panel')).toBeNull()
    expect(textarea().value).toBe('Tomorrow is deadline.')
  })

  it('file attachment rejects files larger than 10 MB and accepts valid files with preview', async () => {
    const onSend = vi.fn()
    render(<MessageComposer onSend={onSend} />)

    const fileInput = screen.getByTestId('file-upload-input')

    // 1. Oversized file (11 MB)
    const largeFile = new File(['a'.repeat(100)], 'huge_document.pdf', { type: 'application/pdf' })
    Object.defineProperty(largeFile, 'size', { value: 11 * 1024 * 1024 })

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [largeFile] } })
    })

    expect(screen.getByTestId('attachment-error-banner')).toHaveTextContent(/exceeds the 10 MB limit/i)
    expect(screen.queryByTestId('attachment-preview-dock')).toBeNull()

    // 2. Valid file (2 MB image)
    const validImage = new File(['image-bytes'], 'screenshot.png', { type: 'image/png' })
    Object.defineProperty(validImage, 'size', { value: 2 * 1024 * 1024 })

    await act(async () => {
      fireEvent.change(fileInput, { target: { files: [validImage] } })
    })

    expect(screen.queryByTestId('attachment-error-banner')).toBeNull()
    expect(screen.getByTestId('attachment-preview-dock')).toBeInTheDocument()
    expect(screen.getByTestId('attachment-name')).toHaveTextContent('screenshot.png')
    expect(screen.getByTestId('attachment-size')).toHaveTextContent('2.0 MB')

    // 3. Remove attachment
    await act(async () => {
      fireEvent.click(screen.getByTestId('remove-attachment-btn'))
    })
    expect(screen.queryByTestId('attachment-preview-dock')).toBeNull()
  })
})

