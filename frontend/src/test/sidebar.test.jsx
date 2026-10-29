import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { Sidebar } from '../components/layout/Sidebar'
import { UserSearchDialog } from '../components/layout/UserSearchDialog'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'
import { conversationService } from '../services/conversationService'
import { authService } from '../services/authService'
import { aiService } from '../services/aiService'
import { setTokens } from '../services/apiClient'

vi.mock('../services/conversationService', () => ({
  conversationService: {
    listConversations: vi.fn(),
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

vi.mock('../services/authService', () => ({
  authService: {
    searchUsers: vi.fn(),
    getCurrentUser: vi.fn().mockResolvedValue({ id: 'u-self', username: 'my_user' }),
    logout: vi.fn(),
    uploadAvatar: vi.fn(),
  },
}))

describe('Sidebar and User Discovery Components', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    setTokens('test-jwt-token', 'test-refresh-token')
    localStorage.setItem('ar_user', JSON.stringify({ id: 'u-self', username: 'my_user' }))
  })

  it('renders Sidebar with separated Direct Messages and Groups sections', async () => {
    conversationService.listConversations.mockResolvedValueOnce([
      {
        id: 'conv-dm-1',
        is_group: false,
        other_participant: { username: 'elena', display_name: 'Elena Rostova' },
        last_message: { content: 'Sounds good!' },
        updated_at: new Date().toISOString(),
      },
      {
        id: 'conv-grp-1',
        is_group: true,
        title: 'Sprint Planning',
        last_message: { content: 'Meeting at 3pm' },
        updated_at: new Date().toISOString(),
      },
    ])

    render(
      <AuthProvider>
        <ChatProvider>
          <Sidebar />
        </ChatProvider>
      </AuthProvider>
    )

    expect(screen.getByText('Direct Messages')).toBeInTheDocument()
    expect(screen.getByText('Groups')).toBeInTheDocument()
    expect(screen.getByText('Alignment Radar')).toBeInTheDocument()

    await waitFor(() => {
      expect(screen.getByText('Elena Rostova')).toBeInTheDocument()
      expect(screen.getByText('Sprint Planning')).toBeInTheDocument()
    })
  })

  it('searches users and starts direct conversation in UserSearchDialog', async () => {
    authService.searchUsers.mockResolvedValueOnce([
      { id: 'u-1', username: 'kavitha', display_name: 'Kavitha R' },
    ])
    conversationService.listConversations.mockResolvedValue([])
    conversationService.getDirectConversation.mockResolvedValueOnce({
      id: 'conv-new-1',
      is_group: false,
    })

    const onClose = vi.fn()
    render(
      <AuthProvider>
        <ChatProvider>
          <UserSearchDialog isOpen={true} onClose={onClose} />
        </ChatProvider>
      </AuthProvider>
    )

    const searchInput = screen.getByPlaceholderText(/search by username/i)
    fireEvent.change(searchInput, { target: { value: 'kavitha' } })

    await waitFor(() => {
      expect(screen.getByText('Kavitha R')).toBeInTheDocument()
      expect(screen.getByText('@kavitha')).toBeInTheDocument()
    })

    const chatBtn = screen.getByRole('button', { name: /chat/i })
    fireEvent.click(chatBtn)

    await waitFor(() => {
      expect(conversationService.getDirectConversation).toHaveBeenCalledWith('kavitha')
      expect(onClose).toHaveBeenCalled()
    })
  })

  it('uploads a new profile picture and shows it immediately in the sidebar', async () => {
    conversationService.listConversations.mockResolvedValue([])
    authService.uploadAvatar.mockResolvedValueOnce({
      id: 'u-self',
      username: 'my_user',
      avatar_url: '/api/v1/users/u-self/avatar',
    })

    render(
      <AuthProvider>
        <ChatProvider>
          <Sidebar />
        </ChatProvider>
      </AuthProvider>
    )

    const fileInput = screen.getByTestId('avatar-file-input')
    const file = new File(['fake-image-bytes'], 'me.png', { type: 'image/png' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(authService.uploadAvatar).toHaveBeenCalledWith(file)
    })

    await waitFor(() => {
      const img = screen.getByAltText('my_user')
      expect(img.getAttribute('src')).toContain('/api/v1/users/u-self/avatar')
    })
  })

  it('shows an error and keeps the previous picture when the avatar upload fails', async () => {
    conversationService.listConversations.mockResolvedValue([])
    authService.uploadAvatar.mockRejectedValueOnce({
      response: { data: { detail: 'Unsupported image type.' } },
    })

    render(
      <AuthProvider>
        <ChatProvider>
          <Sidebar />
        </ChatProvider>
      </AuthProvider>
    )

    const fileInput = screen.getByTestId('avatar-file-input')
    const file = new File(['not-an-image'], 'evil.exe', { type: 'application/octet-stream' })
    fireEvent.change(fileInput, { target: { files: [file] } })

    await waitFor(() => {
      expect(screen.getByTestId('avatar-upload-error')).toHaveTextContent('Unsupported image type.')
    })
    expect(screen.queryByAltText('my_user')).not.toBeInTheDocument()
  })
})
