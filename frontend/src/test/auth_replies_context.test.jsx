import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MessageBubble } from '../components/chat/MessageBubble'
import { MessageComposer } from '../components/chat/MessageComposer'
import { ContextSuggestionCard } from '../components/ai/ContextSuggestionCard'
import { ChatProvider, useChat } from '../context/ChatContext'
import { AuthProvider } from '../context/AuthContext'

vi.mock('../services/authService', () => ({
  authService: {
    getCurrentUser: vi.fn().mockResolvedValue({ id: 'usr-self', username: 'navin', email: 'navin@example.com' }),
    loginWithPassword: vi.fn(),
    logout: vi.fn(),
  },
}))

vi.mock('../services/socketService', () => ({
  socketService: {
    on: vi.fn(),
    off: vi.fn(),
    emit: vi.fn(),
    sendMessage: vi.fn(),
    getStatus: vi.fn().mockReturnValue('connected'),
    onStatusChange: vi.fn().mockReturnValue(() => {}),
    joinConversation: vi.fn(),
    leaveConversation: vi.fn(),
  },
}))

vi.mock('../services/conversationService', () => ({
  conversationService: {
    getMessages: vi.fn().mockResolvedValue({ messages: [], has_more: false }),
    getContextGraph: vi.fn().mockResolvedValue({ active_nodes: [], inconsistencies: [] }),
    deleteMessage: vi.fn().mockResolvedValue({}),
    dismissInconsistency: vi.fn().mockResolvedValue({}),
    resolveInconsistency: vi.fn().mockResolvedValue({}),
    resolveNode: vi.fn().mockResolvedValue({}),
    listConversations: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('../services/aiService', () => ({
  aiService: {
    getAiItems: vi.fn().mockResolvedValue({ findings: [], recommendations: [] }),
    analyzeDraft: vi.fn().mockResolvedValue({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: false,
    }),
  },
}))

describe('Feature Two: Reply-to-Message UI & Gestures', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('ar_access_token', 'mock-token')
  })

  it('renders quoted parent message in MessageBubble when reply_to is present', () => {
    const replyMessage = {
      id: 'msg-101',
      conversation_id: 'conv-1',
      sender_id: 'usr-self',
      sender_username: 'navin',
      content: 'I will review this today.',
      created_at: new Date().toISOString(),
      reply_to: {
        id: 'msg-100',
        sender_id: 'usr-2',
        sender_username: 'alex',
        content: 'Can you check the pull request?',
        has_attachment: false,
        is_deleted_for_everyone: false,
      },
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={replyMessage} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByTestId('quoted-reply-msg-100')).toBeInTheDocument()
    expect(screen.getByText('@alex')).toBeInTheDocument()
    expect(screen.getByText('Can you check the pull request?')).toBeInTheDocument()
    expect(screen.getByText('I will review this today.')).toBeInTheDocument()
  })

  it('masks deleted parent messages in reply quote to "This message was deleted."', () => {
    const replyToDeleted = {
      id: 'msg-102',
      conversation_id: 'conv-1',
      sender_id: 'usr-self',
      sender_username: 'navin',
      content: 'Why did you remove that?',
      created_at: new Date().toISOString(),
      reply_to: {
        id: 'msg-99',
        sender_id: 'usr-2',
        sender_username: 'alex',
        content: 'Original confidential text',
        has_attachment: true,
        is_deleted_for_everyone: true,
      },
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={replyToDeleted} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByTestId('quoted-reply-msg-99')).toBeInTheDocument()
    expect(screen.getByText('This message was deleted.')).toBeInTheDocument()
    expect(screen.queryByText('Original confidential text')).not.toBeInTheDocument()
    expect(screen.queryByText('Attachment')).not.toBeInTheDocument()
  })

  it('renders attachment indicator in quote when original message has an attachment', () => {
    const replyWithAttachment = {
      id: 'msg-103',
      conversation_id: 'conv-1',
      sender_id: 'usr-self',
      content: 'Thanks for sending the document.',
      created_at: new Date().toISOString(),
      reply_to: {
        id: 'msg-98',
        sender_id: 'usr-2',
        sender_username: 'alex',
        content: 'Here is the report.',
        has_attachment: true,
        is_deleted_for_everyone: false,
      },
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={replyWithAttachment} />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText('Attachment')).toBeInTheDocument()
  })

  it('provides desktop quick reply button on hover', () => {
    const msg = {
      id: 'msg-104',
      conversation_id: 'conv-1',
      sender_id: 'usr-2',
      sender_username: 'alex',
      content: 'Good morning!',
      created_at: new Date().toISOString(),
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={msg} />
        </ChatProvider>
      </AuthProvider>
    )

    const replyBtn = screen.getByTestId('reply-btn-msg-104')
    expect(replyBtn).toBeInTheDocument()
    fireEvent.click(replyBtn)
  })

  it('supports touch swipe-to-reply gesture past threshold (dx >= 45px)', () => {
    const msg = {
      id: 'msg-105',
      conversation_id: 'conv-1',
      sender_id: 'usr-2',
      sender_username: 'alex',
      content: 'Swipe me to reply',
      created_at: new Date().toISOString(),
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={msg} />
        </ChatProvider>
      </AuthProvider>
    )

    const bubbleContainer = screen.getByText('Swipe me to reply').closest('#msg-msg-105')
    expect(bubbleContainer).toBeInTheDocument()

    // Touch start
    fireEvent.touchStart(bubbleContainer, {
      touches: [{ clientX: 50, clientY: 100 }],
    })

    // Touch move horizontally past 45px
    fireEvent.touchMove(bubbleContainer, {
      touches: [{ clientX: 110, clientY: 100 }],
    })

    expect(screen.getByTestId('swipe-reply-indicator')).toBeInTheDocument()

    // Touch end activates reply
    fireEvent.touchEnd(bubbleContainer)
  })

  it('does NOT trigger swipe-to-reply on vertical scrolling', () => {
    const msg = {
      id: 'msg-106',
      conversation_id: 'conv-1',
      sender_id: 'usr-2',
      sender_username: 'alex',
      content: 'Scroll past me vertically',
      created_at: new Date().toISOString(),
    }

    render(
      <AuthProvider>
        <ChatProvider>
          <MessageBubble message={msg} />
        </ChatProvider>
      </AuthProvider>
    )

    const bubbleContainer = screen.getByText('Scroll past me vertically').closest('#msg-msg-106')

    // Touch start
    fireEvent.touchStart(bubbleContainer, {
      touches: [{ clientX: 50, clientY: 100 }],
    })

    // Touch move vertically (dy > dx)
    fireEvent.touchMove(bubbleContainer, {
      touches: [{ clientX: 52, clientY: 160 }],
    })

    expect(screen.queryByTestId('swipe-reply-indicator')).toBeNull()

    // Touch end
    fireEvent.touchEnd(bubbleContainer)
  })
})

describe('Feature Three: Live Conversation Context Graph UI', () => {
  it('renders ContextSuggestionCard with title, description, and clarification prompt', () => {
    const inconsistency = {
      id: 'inc-1',
      conversation_id: 'conv-1',
      title: 'Submission status check',
      description: 'Potential discrepancy between earlier commitment and later update',
      clarification_prompt: 'Your earlier message mentioned finishing tonight. Would you like to clarify?',
      earlier_evidence_message_id: 'msg-1',
      later_evidence_message_id: 'msg-2',
      status: 'detected',
      is_dismissed: false,
    }

    const onClarify = vi.fn()
    const onViewContext = vi.fn()
    const onDismiss = vi.fn()
    const onResolve = vi.fn()

    render(
      <ContextSuggestionCard
        inconsistency={inconsistency}
        onClarify={onClarify}
        onViewContext={onViewContext}
        onDismiss={onDismiss}
        onResolve={onResolve}
      />
    )

    expect(screen.getByTestId('context-suggestion-card')).toBeInTheDocument()
    expect(screen.getByText(/Context Check: Submission status check/i)).toBeInTheDocument()
    expect(screen.getByText(/Potential discrepancy/i)).toBeInTheDocument()
    expect(screen.getByText(/"Your earlier message mentioned finishing tonight. Would you like to clarify\?"/i)).toBeInTheDocument()

    // Clarify button
    const clarifyBtn = screen.getByTestId('clarify-context-btn')
    fireEvent.click(clarifyBtn)
    expect(onClarify).toHaveBeenCalledWith(inconsistency.clarification_prompt)

    // View evidence button
    const evidenceBtn = screen.getByTestId('view-context-evidence-btn')
    fireEvent.click(evidenceBtn)
    expect(onViewContext).toHaveBeenCalledWith('msg-1', 'msg-2')

    // Resolve button
    const resolveBtn = screen.getByTestId('resolve-context-btn')
    fireEvent.click(resolveBtn)
    expect(onResolve).toHaveBeenCalledWith('inc-1')

    // Dismiss button
    const dismissBtn = screen.getByTestId('dismiss-context-suggestion-btn')
    fireEvent.click(dismissBtn)
    expect(onDismiss).toHaveBeenCalledWith('inc-1')
  })

  it('does not render dismissed or resolved inconsistencies', () => {
    const dismissedInc = {
      id: 'inc-2',
      title: 'Resolved topic',
      clarification_prompt: 'Already fixed',
      is_dismissed: true,
      status: 'dismissed',
    }

    const { container } = render(
      <ContextSuggestionCard
        inconsistency={dismissedInc}
        onClarify={vi.fn()}
      />
    )

    expect(container.firstChild).toBeNull()
  })
})
