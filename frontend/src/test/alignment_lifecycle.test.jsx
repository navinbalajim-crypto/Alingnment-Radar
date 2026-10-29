import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { AlignmentFindingCard } from '../components/ai/AlignmentFindingCard'
import { RecommendationCard } from '../components/ai/RecommendationCard'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'
import { aiService } from '../services/aiService'

vi.mock('../services/aiService', () => ({
  aiService: {
    getAiItems: vi.fn(),
    confirmAlignment: vi.fn(),
    resolveAlignment: vi.fn(),
    dismissAlignment: vi.fn(),
    shareRecommendation: vi.fn(),
    dismissRecommendation: vi.fn(),
  },
}))

describe('Alignment Lifecycle & Actions Frontend Flow', () => {
  it('renders card in detected state with Clarify and Suggest Reply actions', () => {
    const mockFinding = {
      id: 'find-det-1',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'deadlines',
      title: 'Ambiguous Delivery Date',
      status: 'detected',
      explanation: 'Deadline is stated as "tomorrow" without timezone.',
      confidence: 0.90,
      clarification_question: 'What time tomorrow are you delivering?',
      suggested_reply: 'Could we align on Friday 4 PM EST?',
      confirmations: [],
    }

    const onApply = vi.fn()

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} onApplyQuestion={onApply} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText(/Detected/i)).toBeInTheDocument()
    expect(screen.getByText(/Ambiguous Delivery Date/i)).toBeInTheDocument()
    expect(screen.getByText(/"What time tomorrow are you delivering\?"*/i)).toBeInTheDocument()

    // Clarify button
    const clarifyBtn = screen.getByRole('button', { name: /^clarify$/i })
    expect(clarifyBtn).toBeInTheDocument()
    fireEvent.click(clarifyBtn)
    expect(onApply).toHaveBeenCalledWith('What time tomorrow are you delivering?')

    // Suggest reply button
    const suggestBtn = screen.getByRole('button', { name: /suggest reply/i })
    expect(suggestBtn).toBeInTheDocument()
    fireEvent.click(suggestBtn)
    expect(onApply).toHaveBeenCalledWith('Could we align on Friday 4 PM EST?')
  })

  it('renders card in clarifying state with activity indicator and status', () => {
    const mockFinding = {
      id: 'find-clar-2',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'scope',
      title: 'Release Scope Under Discussion',
      status: 'clarifying',
      explanation: 'Participants are actively discussing billing scope.',
      confidence: 0.88,
      clarification_question: 'Is billing included in v1?',
      confirmations: [],
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText(/Clarifying in Progress/i)).toBeInTheDocument()
  })

  it('renders card in awaiting_confirmation state and triggers confirmation', async () => {
    aiService.confirmAlignment.mockResolvedValueOnce({
      id: 'find-await-3',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      status: 'resolved',
      category: 'scope',
      explanation: 'Scope settled.',
      confidence: 0.95,
      resolution_evidence: 'Agreed on Friday 5 PM EST with v1.2',
      confirmations: [{ user_id: 'u-1', username: 'alice' }],
    })

    const mockFinding = {
      id: 'find-await-3',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'scope',
      title: 'Release Version',
      status: 'awaiting_confirmation',
      explanation: 'Scope settled but needs confirmation.',
      confidence: 0.95,
      resolution_evidence: 'Agreed on Friday 5 PM EST with v1.2',
      confirmations: [{ user_id: 'u-1', username: 'alice' }],
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText(/Awaiting Confirmation/i)).toBeInTheDocument()
    expect(screen.getByText(/Agreed on Friday 5 PM EST with v1.2/i)).toBeInTheDocument()
    expect(screen.getByText(/@alice/i)).toBeInTheDocument()

    const confirmBtn = screen.getByRole('button', { name: /confirm alignment/i })
    expect(confirmBtn).toBeInTheDocument()
    fireEvent.click(confirmBtn)
    await waitFor(() => {
      expect(aiService.confirmAlignment).toHaveBeenCalledWith('conv-1', 'find-await-3', { comment: null })
    })
  })

  it('renders card in resolved state with Alignment Verified badge and hides actions', () => {
    const mockFinding = {
      id: 'find-res-4',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'deadlines',
      title: 'Aligned Schedule',
      status: 'resolved',
      explanation: 'Target locked.',
      confidence: 0.98,
      resolution_evidence: 'Both parties agreed on Friday 5 PM EST',
      confirmations: [
        { user_id: 'u-1', username: 'alice' },
        { user_id: 'u-2', username: 'bob' },
      ],
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText(/Alignment Verified/i)).toBeInTheDocument()
    expect(screen.getByText(/Both parties agreed on Friday 5 PM EST/i)).toBeInTheDocument()
    expect(screen.getByText(/@alice/i)).toBeInTheDocument()
    expect(screen.getByText(/@bob/i)).toBeInTheDocument()

    // In resolved state, action buttons (Clarify, Confirm Alignment) should not be present
    expect(screen.queryByRole('button', { name: /confirm alignment/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /clarify/i })).not.toBeInTheDocument()
  })

  it('allows dismissing an alignment finding', async () => {
    aiService.dismissAlignment.mockResolvedValueOnce({
      id: 'find-5',
      status: 'dismissed',
    })

    const mockFinding = {
      id: 'find-5',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'other',
      explanation: 'Not needed.',
      confidence: 0.70,
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} />
        </ChatProvider>
      </AuthProvider>
    )

    const dismissBtn = screen.getByTitle(/dismiss finding/i)
    fireEvent.click(dismissBtn)

    await waitFor(() => {
      expect(screen.queryByText(/Not needed/i)).not.toBeInTheDocument()
    })
  })

  it('allows dismissing a recommendation card', async () => {
    aiService.dismissRecommendation.mockResolvedValueOnce({
      id: 'rec-dismiss-1',
      is_dismissed: true,
    })

    const mockRec = {
      id: 'rec-dismiss-1',
      conversation_id: 'conv-1',
      source: 'youtube',
      title: 'ICC World Cup Highlights',
      url: 'https://youtube.com/watch?v=icc123',
      is_shared_in_chat: false,
      is_dismissed: false,
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <RecommendationCard recommendation={mockRec} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText('ICC World Cup Highlights')).toBeInTheDocument()
    const dismissBtn = screen.getByTitle(/dismiss recommendation/i)
    fireEvent.click(dismissBtn)

    await waitFor(() => {
      expect(screen.queryByText('ICC World Cup Highlights')).not.toBeInTheDocument()
    })
  })

  it('allows submitting an interactive clarification answer from a participant', async () => {
    aiService.confirmAlignment.mockResolvedValueOnce({
      id: 'finding-clarify-1',
      conversation_id: 'conv-1',
      status: 'awaiting_confirmation',
      confirmations: [
        {
          user_id: 'user-1',
          username: 'alice',
          confirmed_at: new Date().toISOString(),
          comment: 'The report must be uploaded by 5 PM IST tomorrow.',
        },
      ],
    })

    const mockFinding = {
      id: 'finding-clarify-1',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'deadlines',
      title: 'Ambiguous Submission Deadline',
      explanation: 'Submission deadline time is unspecified.',
      clarification_question: 'What is the submission deadline, including expected time?',
      confidence: 0.90,
      status: 'detected',
      confirmations: [],
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} />
        </ChatProvider>
      </AuthProvider>
    )

    // Open answer input
    const answerToggleBtn = screen.getByTestId('clarify-answer-toggle-btn')
    fireEvent.click(answerToggleBtn)

    const input = screen.getByTestId('clarification-input')
    fireEvent.change(input, { target: { value: 'The report must be uploaded by 5 PM IST tomorrow.' } })

    const submitBtn = screen.getByTestId('submit-clarification-btn')
    fireEvent.click(submitBtn)

    await waitFor(() => {
      expect(aiService.confirmAlignment).toHaveBeenCalledWith(
        'conv-1',
        'finding-clarify-1',
        { comment: 'The report must be uploaded by 5 PM IST tomorrow.' }
      )
    })
  })
})
