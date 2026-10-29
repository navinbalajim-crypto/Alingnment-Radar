import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { CreateGroupDialog } from '../components/groups/CreateGroupDialog'
import { GroupDetails } from '../components/groups/GroupDetails'
import { JoinGroupPage } from '../components/groups/JoinGroupPage'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'
import { groupService } from '../services/groupService'
import { invitationService } from '../services/invitationService'
import { conversationService } from '../services/conversationService'
import { aiService } from '../services/aiService'

vi.mock('../services/groupService', () => ({
  groupService: {
    createGroup: vi.fn(),
    getGroup: vi.fn(),
    getMembers: vi.fn(),
    createInvitation: vi.fn(),
  },
}))

vi.mock('../services/invitationService', () => ({
  invitationService: {
    previewInvitation: vi.fn(),
    requestCode: vi.fn(),
    verifyCode: vi.fn(),
    completeRegistration: vi.fn(),
  },
}))

vi.mock('../services/conversationService', () => ({
  conversationService: {
    listConversations: vi.fn().mockResolvedValue([]),
    getDirectConversation: vi.fn(),
    getMessages: vi.fn().mockResolvedValue({ messages: [], has_more: false }),
  },
}))

vi.mock('../services/aiService', () => ({
  aiService: {
    getAiItems: vi.fn().mockResolvedValue({ findings: [], recommendations: [] }),
    shareRecommendation: vi.fn(),
  },
}))

describe('Groups and Invitation Components', () => {
  it('submits CreateGroupDialog with title and initial member usernames', async () => {
    groupService.createGroup.mockResolvedValueOnce({
      id: 'grp-1',
      title: 'Design Systems',
      members: [],
    })

    const onClose = vi.fn()
    render(
      <AuthProvider>
        <ChatProvider>
          <CreateGroupDialog isOpen={true} onClose={onClose} />
        </ChatProvider>
      </AuthProvider>
    )

    const titleInput = screen.getByLabelText(/group title/i)
    fireEvent.change(titleInput, { target: { value: 'Design Systems' } })

    const membersInput = screen.getByLabelText(/initial members/i)
    fireEvent.change(membersInput, { target: { value: 'alex, sarah' } })

    const createBtn = screen.getByRole('button', { name: /create group/i })
    fireEvent.click(createBtn)

    await waitFor(() => {
      expect(groupService.createGroup).toHaveBeenCalledWith('Design Systems', ['alex', 'sarah'])
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('renders JoinGroupPage with group preview details', async () => {
    invitationService.previewInvitation.mockResolvedValueOnce({
      group_id: 'grp-1',
      group_title: 'Core AI Alignment Team',
      invited_by_username: 'superadmin',
      is_valid: true,
      expires_at: new Date(Date.now() + 86400000).toISOString(),
    })

    render(
      <MemoryRouter initialEntries={['/invitations/token-123']}>
        <AuthProvider>
          <Routes>
            <Route path="/invitations/:token" element={<JoinGroupPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText('Core AI Alignment Team')).toBeInTheDocument()
      expect(screen.getByText(/@superadmin/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /get join code/i })).toBeInTheDocument()
    })
  })
})
