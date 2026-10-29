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
    shareRecommendation: vi.fn(),
  },
}))

describe('Inline AI Components', () => {
  it('renders AlignmentFindingCard with category, explanation, and clarification question', () => {
    const mockFinding = {
      id: 'find-1',
      conversation_id: 'conv-1',
      mismatch_detected: true,
      category: 'deadlines',
      explanation: 'Person A expects deployment Friday morning, while Person B stated Friday evening.',
      confidence: 0.94,
      supporting_message_ids: ['msg-10', 'msg-11'],
      clarification_question: 'Could we confirm the exact target time for the Friday deployment?',
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <AlignmentFindingCard finding={mockFinding} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText(/Timeline & Deadline Discrepancy/i)).toBeInTheDocument()
    expect(screen.getByText(/Person A expects deployment Friday morning/i)).toBeInTheDocument()
    expect(screen.getByText(/94% AI Confidence/i)).toBeInTheDocument()
    expect(screen.getByText(/"Could we confirm the exact target time for the Friday deployment\?"*/i)).toBeInTheDocument()
    expect(screen.getByText(/Message #1/i)).toBeInTheDocument()
    expect(screen.getByText(/Message #2/i)).toBeInTheDocument()
  })

  it('renders RecommendationCard and triggers Share in Chat', async () => {
    aiService.shareRecommendation.mockResolvedValueOnce({
      id: 'shared-msg-1',
      conversation_id: 'conv-1',
      content: 'Enjoy Enjaami',
      message_type: 'link_share',
    })

    const mockRec = {
      id: 'rec-1',
      conversation_id: 'conv-1',
      source: 'Spotify',
      title: 'Enjoy Enjaami',
      url: 'https://open.spotify.com/track/enjoy-enjaami',
      snippet: 'Tamil viral hit by Dhee and Arivu.',
      category: 'music',
      extra_data: {
        artist: 'Dhee ft. Arivu',
      },
      is_shared_in_chat: false,
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <RecommendationCard recommendation={mockRec} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText('Enjoy Enjaami')).toBeInTheDocument()
    expect(screen.getByText(/by Dhee ft. Arivu/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /open link/i })).toHaveAttribute(
      'href',
      'https://open.spotify.com/track/enjoy-enjaami'
    )

    const shareBtn = screen.getByRole('button', { name: /share in chat/i })
    expect(shareBtn).toBeInTheDocument()
  })
})
