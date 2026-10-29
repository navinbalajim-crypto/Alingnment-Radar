import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MessageBubble } from '../components/chat/MessageBubble'
import { MessageComposer } from '../components/chat/MessageComposer'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'

// Mock socketService
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
    on: vi.fn(),
    off: vi.fn(),
  },
}))

describe('Chat Message Components', () => {
  it('renders a text message bubble correctly', () => {
    const mockMessage = {
      id: 'msg-1',
      conversation_id: 'conv-1',
      sender_id: 'user-2',
      sender_username: 'sarah_connor',
      content: 'Let us deploy the website Friday evening.',
      message_type: 'text',
      msg_metadata: {},
      created_at: new Date().toISOString(),
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={mockMessage} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText('Let us deploy the website Friday evening.')).toBeInTheDocument()
    expect(screen.getByText('@sarah_connor')).toBeInTheDocument()
  })

  it('renders a link_share message bubble with link card', () => {
    const mockLinkMsg = {
      id: 'msg-link-1',
      conversation_id: 'conv-1',
      sender_id: 'user-1',
      sender_username: 'alex',
      content: 'Check out this song on Spotify',
      message_type: 'link_share',
      msg_metadata: {
        source: 'Spotify',
        url: 'https://open.spotify.com/track/123',
        title: 'Enjoy Enjaami',
      },
      created_at: new Date().toISOString(),
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={mockLinkMsg} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText(/Shared Spotify/i)).toBeInTheDocument()
    expect(screen.getByText('Enjoy Enjaami')).toBeInTheDocument()
    expect(screen.getByRole('link')).toHaveAttribute('href', 'https://open.spotify.com/track/123')
  })

  it('MessageComposer sends message on Enter key', () => {
    const onSend = vi.fn()
    render(
      <AuthProvider>
        <ChatProvider>
          <MessageComposer onSend={onSend} />
        </ChatProvider>
      </AuthProvider>
    )

    const textarea = screen.getByPlaceholderText(/message or ask for alignment/i)
    fireEvent.change(textarea, { target: { value: 'Hello team!' } })

    // Press Enter without shift
    fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false })
    expect(onSend).toHaveBeenCalledWith('Hello team!')
  })
})
