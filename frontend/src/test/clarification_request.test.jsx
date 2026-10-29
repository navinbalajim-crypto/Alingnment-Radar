import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AlignmentFindingCard } from '../components/ai/AlignmentFindingCard'
import { MessageBubble } from '../components/chat/MessageBubble'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'
import { aiService } from '../services/aiService'

vi.mock('../services/aiService', () => ({
  aiService: {
    getAiItems: vi.fn(),
    confirmAlignment: vi.fn(),
    resolveAlignment: vi.fn(),
    dismissAlignment: vi.fn(),
    requestClarification: vi.fn(),
    triggerAlignment: vi.fn(),
  },
}))

const finding = {
  id: 'f-1',
  conversation_id: 'c-1',
  mismatch_detected: true,
  category: 'unclear_references',
  title: 'Unclear Submission Target',
  status: 'detected',
  explanation: 'It is unclear what must be submitted.',
  confidence: 0.9,
  supporting_message_ids: ['m-1'],
  clarification_question: 'Which assignment?',
  confirmations: [],
}

const wrap = (ui) => render(<AuthProvider><ChatProvider>{ui}</ChatProvider></AuthProvider>)

describe('Receiver-initiated clarification', () => {
  it('shows an explicit Ask for clarification action and calls the API once on click', async () => {
    aiService.requestClarification.mockResolvedValueOnce({ ...finding, status: 'clarifying', clarification_request_message_id: 'm-2' })
    wrap(<AlignmentFindingCard finding={finding} />)

    fireEvent.click(screen.getByTestId('request-clarification-btn'))
    await waitFor(() => expect(aiService.requestClarification).toHaveBeenCalledWith('c-1', 'f-1'))
    expect(aiService.requestClarification).toHaveBeenCalledTimes(1)
  })

  it('does not offer the action again once a request exists', () => {
    wrap(<AlignmentFindingCard finding={{ ...finding, status: 'clarifying', clarification_request_message_id: 'm-2' }} />)
    expect(screen.queryByTestId('request-clarification-btn')).toBeNull()
    expect(screen.getByTestId('clarification-requested')).toBeInTheDocument()
  })

  it('renders the clarification request message distinctly in the chat', () => {
    wrap(
      <MessageBubble
        message={{
          id: 'm-2',
          conversation_id: 'c-1',
          sender_id: 'u-b',
          sender_username: 'bob',
          content: '@bob asks for clarification on "Submit it tomorrow.": Which assignment?',
          message_type: 'ai_alignment',
          msg_metadata: { kind: 'clarification_request', finding_id: 'f-1' },
          created_at: new Date().toISOString(),
        }}
      />
    )
    expect(screen.getByTestId('clarification-request-label')).toBeInTheDocument()
    expect(screen.getByText(/Submit it tomorrow/)).toBeInTheDocument()
  })
})
