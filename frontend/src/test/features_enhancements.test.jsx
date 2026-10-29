import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MessageBubble } from '../components/chat/MessageBubble'
import { GroupDetails } from '../components/groups/GroupDetails'
import { MessageComposer } from '../components/chat/MessageComposer'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'
import { groupService } from '../services/groupService'
import { conversationService } from '../services/conversationService'
import { aiService } from '../services/aiService'

vi.mock('../services/groupService', () => ({
  groupService: {
    getGroup: vi.fn(),
    getMembers: vi.fn(),
    promoteMember: vi.fn(),
    removeMember: vi.fn(),
    uploadGroupAvatar: vi.fn(),
    removeGroupAvatar: vi.fn(),
  },
}))

vi.mock('../services/conversationService', () => ({
  conversationService: {
    listConversations: vi.fn().mockResolvedValue([]),
    getMessages: vi.fn().mockResolvedValue({ messages: [], has_more: false }),
    deleteMessage: vi.fn().mockResolvedValue({ status: 'success' }),
  },
}))

vi.mock('../services/aiService', () => ({
  aiService: {
    getAiItems: vi.fn().mockResolvedValue({ findings: [], recommendations: [] }),
  },
}))

const mockUser = { id: 'usr-1', username: 'alice', display_name: 'Alice' }

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isAuthenticated: true,
  }),
  AuthProvider: ({ children }) => <div>{children}</div>,
}))

describe('Feature Enhancements Component Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  describe('MessageBubble', () => {
    it('renders "This message was deleted." placeholder when deleted for everyone', () => {
      const deletedMessage = {
        id: 'msg-1',
        conversation_id: 'conv-1',
        sender_id: 'usr-1',
        content: 'This message was deleted.',
        is_deleted_for_everyone: true,
        created_at: new Date().toISOString(),
      }

      render(
        <ChatProvider>
          <MessageBubble message={deletedMessage} />
        </ChatProvider>
      )

      expect(screen.getByTestId('deleted-message-indicator')).toBeInTheDocument()
      expect(screen.getByText('This message was deleted.')).toBeInTheDocument()
    })

    it('renders image attachment and document card with download link', () => {
      const attachmentMsg = {
        id: 'msg-2',
        conversation_id: 'conv-1',
        sender_id: 'usr-2',
        sender_username: 'bob',
        content: 'Here are the design assets',
        attachments: [
          {
            id: 'att-1',
            original_filename: 'mockup.png',
            content_type: 'image/png',
            file_size: 204800,
          },
          {
            id: 'att-2',
            original_filename: 'specs.pdf',
            content_type: 'application/pdf',
            file_size: 1048576,
          },
        ],
        created_at: new Date().toISOString(),
      }

      render(
        <ChatProvider>
          <MessageBubble message={attachmentMsg} />
        </ChatProvider>
      )

      expect(screen.getByTestId('message-attachments-container')).toBeInTheDocument()
      expect(screen.getByTestId('attachment-image')).toBeInTheDocument()
      expect(screen.getByTestId('attachment-document')).toBeInTheDocument()
      expect(screen.getByText('specs.pdf')).toBeInTheDocument()
    })

    it('shows action menu with "Delete for me" and "Delete for everyone"', async () => {
      const msg = {
        id: 'msg-3',
        conversation_id: 'conv-1',
        sender_id: 'usr-1',
        sender_username: 'alice',
        content: 'Test message to delete',
        created_at: new Date().toISOString(),
      }

      render(
        <ChatProvider>
          <MessageBubble message={msg} />
        </ChatProvider>
      )

      const optionsBtn = screen.getByTestId('msg-options-btn-msg-3')
      fireEvent.click(optionsBtn)

      expect(screen.getByTestId('delete-for-me-btn')).toBeInTheDocument()
      expect(screen.getByTestId('delete-for-everyone-btn')).toBeInTheDocument()
    })
  })

  describe('GroupDetails Administration', () => {
    it('allows admin to promote a member to admin', async () => {
      groupService.getGroup.mockResolvedValueOnce({
        id: 'grp-1',
        title: 'Alpha Team',
      })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'admin' },
        { id: 'm-2', user_id: 'usr-2', username: 'bob', role: 'member' },
      ])
      groupService.promoteMember.mockResolvedValueOnce({ status: 'success' })

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('@bob')).toBeInTheDocument()
      })

      const promoteBtn = screen.getByTestId('promote-admin-btn-usr-2')
      expect(promoteBtn).toBeInTheDocument()
      fireEvent.click(promoteBtn)

      await waitFor(() => {
        expect(groupService.promoteMember).toHaveBeenCalledWith('grp-1', 'usr-2')
      })
    })

    it('displays confirmation dialog before removing a member', async () => {
      groupService.getGroup.mockResolvedValueOnce({
        id: 'grp-1',
        title: 'Alpha Team',
      })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'admin' },
        { id: 'm-2', user_id: 'usr-2', username: 'bob', role: 'member' },
      ])
      groupService.removeMember.mockResolvedValueOnce({ status: 'success' })

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('@bob')).toBeInTheDocument()
      })

      const removeBtn = screen.getByTestId('remove-member-btn-usr-2')
      fireEvent.click(removeBtn)

      // Confirmation dialog must appear
      expect(screen.getByTestId('remove-member-confirm-dialog')).toBeInTheDocument()
      expect(screen.getByText(/Remove @bob from group\?/i)).toBeInTheDocument()

      const confirmBtn = screen.getByTestId('confirm-remove-btn')
      fireEvent.click(confirmBtn)

      await waitFor(() => {
        expect(groupService.removeMember).toHaveBeenCalledWith('grp-1', 'usr-2')
      })
    })

    it('shows the group avatar in the header area, falling back to initials when unset', async () => {
      groupService.getGroup.mockResolvedValueOnce({ id: 'grp-1', title: 'Alpha Team', avatar_url: null })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'admin' },
      ])

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      await waitFor(() => {
        expect(screen.getByTestId('change-group-avatar-label')).toBeInTheDocument()
      })
      // No avatar_url yet -> falls back to the group icon, not a broken <img>.
      expect(screen.queryByAltText('Alpha Team')).not.toBeInTheDocument()
    })

    it('lets an admin upload a group photo and shows it immediately', async () => {
      groupService.getGroup.mockResolvedValueOnce({ id: 'grp-1', title: 'Alpha Team', avatar_url: null })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'admin' },
      ])
      groupService.uploadGroupAvatar.mockResolvedValueOnce({
        id: 'grp-1',
        avatar_url: '/api/v1/groups/grp-1/avatar?v=123',
      })

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      const fileInput = await screen.findByTestId('group-avatar-file-input')
      const file = new File(['fake-image-bytes'], 'group.png', { type: 'image/png' })
      fireEvent.change(fileInput, { target: { files: [file] } })

      await waitFor(() => {
        expect(groupService.uploadGroupAvatar).toHaveBeenCalledWith('grp-1', file)
      })
      await waitFor(() => {
        const img = screen.getByAltText('Alpha Team')
        expect(img.getAttribute('src')).toContain('/api/v1/groups/grp-1/avatar')
      })
    })

    it('shows an error and keeps the previous group photo when the upload fails', async () => {
      groupService.getGroup.mockResolvedValueOnce({ id: 'grp-1', title: 'Alpha Team', avatar_url: null })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'admin' },
      ])
      groupService.uploadGroupAvatar.mockRejectedValueOnce({
        response: { data: { detail: 'Unsupported image type.' } },
      })

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      const fileInput = await screen.findByTestId('group-avatar-file-input')
      const file = new File(['not-an-image'], 'evil.exe', { type: 'application/octet-stream' })
      fireEvent.change(fileInput, { target: { files: [file] } })

      await waitFor(() => {
        expect(screen.getByTestId('group-avatar-error')).toHaveTextContent('Unsupported image type.')
      })
      expect(screen.queryByAltText('Alpha Team')).not.toBeInTheDocument()
    })

    it('lets an admin remove the group photo after confirming, restoring the default avatar', async () => {
      groupService.getGroup.mockResolvedValueOnce({
        id: 'grp-1',
        title: 'Alpha Team',
        avatar_url: '/api/v1/groups/grp-1/avatar?v=111',
      })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'admin' },
      ])
      groupService.removeGroupAvatar.mockResolvedValueOnce({ id: 'grp-1', avatar_url: null })

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      const removeBtn = await screen.findByTestId('remove-group-avatar-btn')
      fireEvent.click(removeBtn)
      expect(screen.getByText(/Remove the group photo\?/i)).toBeInTheDocument()

      fireEvent.click(screen.getByTestId('confirm-remove-group-avatar-btn'))

      await waitFor(() => {
        expect(groupService.removeGroupAvatar).toHaveBeenCalledWith('grp-1')
      })
      await waitFor(() => {
        expect(screen.queryByTestId('remove-group-avatar-btn')).not.toBeInTheDocument()
      })
    })

    it('does not show change-photo controls to a regular (non-admin) member', async () => {
      groupService.getGroup.mockResolvedValueOnce({ id: 'grp-1', title: 'Alpha Team', avatar_url: null })
      groupService.getMembers.mockResolvedValueOnce([
        { id: 'm-1', user_id: 'usr-1', username: 'alice', role: 'member' },
        { id: 'm-2', user_id: 'usr-2', username: 'bob', role: 'admin' },
      ])

      render(
        <ChatProvider>
          <GroupDetails groupId="grp-1" isOpen={true} onClose={() => {}} />
        </ChatProvider>
      )

      await waitFor(() => {
        expect(screen.getByText('@bob')).toBeInTheDocument()
      })
      expect(screen.queryByTestId('change-group-avatar-label')).not.toBeInTheDocument()
      expect(screen.queryByTestId('remove-group-avatar-btn')).not.toBeInTheDocument()
    })
  })

  describe('MessageComposer Pre-send and Attachments', () => {
    it('rejects files larger than 10 MB on frontend', () => {
      render(
        <ChatProvider>
          <MessageComposer onSend={vi.fn()} />
        </ChatProvider>
      )

      const fileInput = screen.getByTestId('file-upload-input')
      // Create a 11 MB dummy file
      const oversizedFile = new File(['x'.repeat(100)], 'huge_video.mp4', { type: 'video/mp4' })
      Object.defineProperty(oversizedFile, 'size', { value: 11 * 1024 * 1024 })

      fireEvent.change(fileInput, { target: { files: [oversizedFile] } })

      const errorBanner = screen.getByTestId('attachment-error-banner')
      expect(errorBanner).toBeInTheDocument()
      expect(errorBanner).toHaveTextContent(/10 MB/i)
    })

    it('stages a valid file under 10 MB and displays attachment preview', () => {
      render(
        <ChatProvider>
          <MessageComposer onSend={vi.fn()} />
        </ChatProvider>
      )

      const fileInput = screen.getByTestId('file-upload-input')
      const validFile = new File(['valid content'], 'design.png', { type: 'image/png' })
      Object.defineProperty(validFile, 'size', { value: 500000 })

      fireEvent.change(fileInput, { target: { files: [validFile] } })

      expect(screen.getByTestId('attachment-preview-dock')).toBeInTheDocument()
      expect(screen.getByText('design.png')).toBeInTheDocument()
    })
  })
})
