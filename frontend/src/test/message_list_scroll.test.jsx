import React from 'react'
import { render, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MessageList } from '../components/chat/MessageList'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'

vi.mock('../services/socketService', () => ({
  socketService: {
    getStatus: () => 'disconnected',
    onStatusChange: () => () => {},
    on: () => {},
    off: () => {},
    connect: () => {},
    disconnect: () => {},
    joinConversation: () => {},
  },
}))
vi.mock('../services/conversationService', () => ({
  conversationService: { listConversations: () => Promise.resolve([]) },
}))

// jsdom has no real layout engine, so scrollIntoView doesn't exist and scrollHeight/scrollTop
// are always 0. These tests stub exactly what the component reads/calls to verify the real
// decision logic (switch vs prepend vs append), not pixel-perfect scrolling.
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn()
})

function msg(id) {
  return { id, content: 'hi', sender_id: 'u1', created_at: new Date().toISOString() }
}

function Wrapped({ children }) {
  return (
    <AuthProvider>
      <ChatProvider>{children}</ChatProvider>
    </AuthProvider>
  )
}

async function flushRaf() {
  await act(async () => {
    await new Promise((r) => requestAnimationFrame(r))
  })
}

describe('MessageList scroll behaviour', () => {
  it('jumps to the newest message, instantly, when a different conversation is opened -- even with fewer messages than before', async () => {
    const many = Array.from({ length: 20 }, (_, i) => msg(`a${i}`))
    const { rerender } = render(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={many} />
      </Wrapped>
    )
    await flushRaf()
    Element.prototype.scrollIntoView.mockClear()

    const fewer = Array.from({ length: 3 }, (_, i) => msg(`b${i}`))
    rerender(
      <Wrapped>
        <MessageList conversationId="conv-B" messages={fewer} />
      </Wrapped>
    )
    await flushRaf()

    // This is the actual reported bug: fewer messages than before used to mean no scroll at
    // all, leaving the viewport wherever conv-A had left it.
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('does not jump to the bottom when older messages are prepended by "Load older messages"', async () => {
    const initial = Array.from({ length: 10 }, (_, i) => msg(`m${i + 10}`))
    const { rerender, container } = render(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={initial} />
      </Wrapped>
    )
    await flushRaf()
    Element.prototype.scrollIntoView.mockClear()

    const scrollEl = container.querySelector('.overflow-y-auto')
    Object.defineProperty(scrollEl, 'scrollHeight', { value: 2000, configurable: true })
    Object.defineProperty(scrollEl, 'scrollTop', { value: 0, writable: true, configurable: true })

    const withOlderPrepended = [
      ...Array.from({ length: 10 }, (_, i) => msg(`m${i}`)), // older messages prepended
      ...initial,
    ]
    rerender(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={withOlderPrepended} />
      </Wrapped>
    )
    await flushRaf()

    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
  })

  it('scrolls to the newest message when a message is appended and the user was already at the bottom', async () => {
    const initial = Array.from({ length: 5 }, (_, i) => msg(`m${i}`))
    const { rerender, container } = render(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={initial} />
      </Wrapped>
    )
    await flushRaf()
    Element.prototype.scrollIntoView.mockClear()

    const scrollEl = container.querySelector('.overflow-y-auto')
    Object.defineProperty(scrollEl, 'scrollHeight', { value: 500, configurable: true })
    Object.defineProperty(scrollEl, 'scrollTop', { value: 500, configurable: true })
    Object.defineProperty(scrollEl, 'clientHeight', { value: 500, configurable: true })
    scrollEl.dispatchEvent(new Event('scroll'))

    const withNewAppended = [...initial, msg('m-new')]
    rerender(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={withNewAppended} />
      </Wrapped>
    )
    await flushRaf()

    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })

  it('does NOT yank the user to the bottom on a new message when they have scrolled up to read older messages', async () => {
    const initial = Array.from({ length: 5 }, (_, i) => msg(`m${i}`))
    const { rerender, container } = render(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={initial} />
      </Wrapped>
    )
    await flushRaf()
    Element.prototype.scrollIntoView.mockClear()

    const scrollEl = container.querySelector('.overflow-y-auto')
    // Far from the bottom.
    Object.defineProperty(scrollEl, 'scrollHeight', { value: 3000, configurable: true })
    Object.defineProperty(scrollEl, 'scrollTop', { value: 0, configurable: true })
    Object.defineProperty(scrollEl, 'clientHeight', { value: 500, configurable: true })
    scrollEl.dispatchEvent(new Event('scroll'))

    const withNewAppended = [...initial, msg('m-new')]
    rerender(
      <Wrapped>
        <MessageList conversationId="conv-A" messages={withNewAppended} />
      </Wrapped>
    )
    await flushRaf()

    expect(Element.prototype.scrollIntoView).not.toHaveBeenCalled()
  })
})
