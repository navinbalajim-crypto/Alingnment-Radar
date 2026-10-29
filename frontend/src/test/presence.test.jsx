import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ConversationItem } from '../components/chat/ConversationItem'

const chatState = { onlineUserIds: new Set(), groupOnlineCounts: {} }
vi.mock('../context/ChatContext', () => ({
  useChat: () => chatState,
}))

const dm = {
  id: 'conv-dm',
  is_group: false,
  other_participant: { id: 'u-bob', username: 'bob', display_name: 'Bob' },
  last_message: { content: 'hi', created_at: '2026-10-28T15:00:00Z' },
  updated_at: '2026-10-28T15:00:00Z',
}

const group = {
  id: 'conv-grp',
  is_group: true,
  title: 'Team',
  last_message: { content: 'standup?', created_at: '2026-10-28T15:00:00Z' },
  updated_at: '2026-10-28T15:00:00Z',
}

describe('Presence indicators', () => {
  beforeEach(() => {
    chatState.onlineUserIds = new Set()
    chatState.groupOnlineCounts = {}
  })

  it('shows no online dot for an offline DM peer', () => {
    render(<ConversationItem conversation={dm} isSelected={false} onClick={() => {}} />)
    expect(screen.queryByTestId('online-status-dot')).not.toBeInTheDocument()
  })

  it('shows an online dot when the DM peer is online', () => {
    chatState.onlineUserIds = new Set(['u-bob'])
    render(<ConversationItem conversation={dm} isSelected={false} onClick={() => {}} />)
    expect(screen.getByTestId('online-status-dot')).toBeInTheDocument()
  })

  it('shows the live online-member count for a group', () => {
    chatState.groupOnlineCounts = { 'conv-grp': 3 }
    render(<ConversationItem conversation={group} isSelected={false} onClick={() => {}} />)
    expect(screen.getByTestId('group-online-count')).toHaveTextContent('3 online')
  })

  it('hides the group count when nobody is online', () => {
    chatState.groupOnlineCounts = { 'conv-grp': 0 }
    render(<ConversationItem conversation={group} isSelected={false} onClick={() => {}} />)
    expect(screen.queryByTestId('group-online-count')).not.toBeInTheDocument()
  })
})
