import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ConversationHeader } from '../components/layout/ConversationHeader'

const chat = {}
vi.mock('../context/ChatContext', () => ({ useChat: () => chat }))

const dm = { id: 'c1', is_group: false, other_participant: { id: 'u-bob', username: 'bob', display_name: 'Bob' } }

describe('ConversationHeader presence', () => {
  beforeEach(() => {
    Object.assign(chat, {
      socketStatus: 'connected',
      presenceReady: true,
      onlineUserIds: new Set(),
      groupOnlineCounts: {},
      triggerAlignment: vi.fn(),
      requestRecommendations: vi.fn(),
    })
  })

  it('never shows "Real-time active" (that was our own socket status, not theirs)', () => {
    render(<ConversationHeader conversation={dm} />)
    expect(screen.queryByText(/real-time active/i)).not.toBeInTheDocument()
  })

  it('shows Offline with no green dot when the other person is offline', () => {
    render(<ConversationHeader conversation={dm} />)
    expect(screen.getByTestId('header-presence')).toHaveTextContent('Offline')
    expect(screen.queryByTestId('header-online-dot')).not.toBeInTheDocument()
  })

  it('shows Online with the green dot when the other person is online', () => {
    chat.onlineUserIds = new Set(['u-bob'])
    render(<ConversationHeader conversation={dm} />)
    expect(screen.getByTestId('header-presence')).toHaveTextContent('Online')
    expect(screen.getByTestId('header-online-dot')).toBeInTheDocument()
  })

  it('treats unknown presence as Connecting…, not online, even with stale data', () => {
    chat.presenceReady = false
    chat.onlineUserIds = new Set(['u-bob'])
    render(<ConversationHeader conversation={dm} />)
    expect(screen.getByTestId('header-presence')).toHaveTextContent('Connecting…')
    expect(screen.queryByTestId('header-online-dot')).not.toBeInTheDocument()
  })
})
