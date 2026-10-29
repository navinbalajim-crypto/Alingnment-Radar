import React from 'react'
import { render, screen, act, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider, useChat } from '../context/ChatContext'
import { aiService } from '../services/aiService'

const handlers = {}
vi.mock('../services/socketService', () => ({
  socketService: {
    getStatus: () => 'connected',
    onStatusChange: (cb) => {
      cb('connected')
      return () => {}
    },
    connect: vi.fn(),
    disconnect: vi.fn(),
    joinConversation: vi.fn(),
    sendMessage: vi.fn(),
    on: (evt, fn) => {
      handlers[evt] = fn
    },
    off: vi.fn(),
  },
}))
vi.mock('../services/conversationService', () => ({
  conversationService: {
    listConversations: vi.fn().mockResolvedValue([]),
    getMessages: vi.fn().mockResolvedValue({ messages: [], has_more: false }),
  },
}))
vi.mock('../services/aiService', () => ({
  aiService: { getAiItems: vi.fn() },
}))

const mk = (id, conv, status = 'detected') => ({
  id,
  conversation_id: conv,
  mismatch_detected: true,
  category: 'ambiguity',
  title: `T-${id}`,
  status,
  explanation: 'x',
  confidence: 0.9,
  supporting_message_ids: [],
  confirmations: [],
})

function Probe() {
  const { selectConversation, aiFindings } = useChat()
  return (
    <div>
      <button onClick={() => selectConversation('group-1')}>open</button>
      <ul data-testid="ids">{aiFindings.map((f) => <li key={f.id}>{f.id}:{f.status}</li>)}</ul>
    </div>
  )
}

describe('Group conversation event isolation (client side)', () => {
  beforeEach(() => {
    aiService.getAiItems.mockResolvedValue({ findings: [mk('f-a', 'group-1')], recommendations: [] })
  })

  it('ignores findings for other conversations, dedupes replays, and keeps reload state', async () => {
    render(
      <AuthProvider>
        <ChatProvider>
          <Probe />
        </ChatProvider>
      </AuthProvider>
    )
    await act(async () => {
      screen.getByText('open').click()
    })
    await waitFor(() => expect(screen.getByTestId('ids').textContent).toContain('f-a:detected'))

    await act(async () => {
      handlers['ai:alignment']({ finding: mk('f-other', 'group-2') }) // other group's event
      handlers['ai:alignment']({ finding: mk('f-a', 'group-1') }) // replayed event for the same finding
      handlers['ai:alignment']({ finding: mk('f-b', 'group-1') })
      handlers['ai:alignment']({ finding: mk('f-b', 'group-1') }) // duplicate delivery
    })
    const text = screen.getByTestId('ids').textContent
    expect(text).not.toContain('f-other')
    expect(text.match(/f-a/g)).toHaveLength(1)
    expect(text.match(/f-b/g)).toHaveLength(1)

    await act(async () => {
      handlers['ai:alignment_update']({ finding: mk('f-a', 'group-1', 'clarifying') })
      handlers['ai:alignment_update']({ finding: mk('f-other', 'group-2', 'resolved') })
    })
    const after = screen.getByTestId('ids').textContent
    expect(after).toContain('f-a:clarifying')
    expect(after).not.toContain('f-other')
  })
})
