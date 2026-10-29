import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { GoogleCallbackPage } from '../components/auth/GoogleCallbackPage'
import { IntegrationsDialog } from '../components/settings/IntegrationsDialog'
import { GmailNotificationsPopover } from '../components/layout/GmailNotificationsPopover'
import { AuthProvider } from '../context/AuthContext'
import { contactService } from '../services/contactService'
import { gmailService } from '../services/gmailService'
import { authService } from '../services/authService'

vi.mock('../services/contactService', () => ({
  contactService: {
    getGoogleStatus: vi.fn(),
    getContacts: vi.fn(),
    syncGoogleContacts: vi.fn(),
    disconnectGoogle: vi.fn(),
    getGoogleContactsConnectUrl: vi.fn(),
    connectGoogleContacts: vi.fn(),
  },
}))

vi.mock('../services/gmailService', () => ({
  gmailService: {
    getStatus: vi.fn(),
    getConnectUrl: vi.fn(),
    connectGmail: vi.fn(),
    checkMessages: vi.fn(),
    getNotifications: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
    disconnect: vi.fn(),
  },
}))

vi.mock('../services/authService', () => ({
  authService: {
    getGoogleAuthUrl: vi.fn(),
    loginWithGoogle: vi.fn(),
  },
}))

// Helper to craft a mock JWT state string with a specific purpose
function makeMockState(purpose) {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
  const payload = btoa(JSON.stringify({ purpose, jti: 'test1234', exp: 9999999999 }))
  return `${header}.${payload}.signature123`
}

describe('Google Contacts & Gmail Frontend Integrations', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('routes contacts OAuth callback to connectGoogleContacts and navigates to chat', async () => {
    const contactsState = makeMockState('contacts')
    contactService.connectGoogleContacts.mockResolvedValueOnce({
      connected: true,
      email: 'user@gmail.com',
      matched_registered_count: 3,
    })

    render(
      <MemoryRouter initialEntries={[`/auth/google/callback?code=mock_code_contacts&state=${contactsState}`]}>
        <AuthProvider>
          <GoogleCallbackPage />
        </AuthProvider>
      </MemoryRouter>
    )

    expect(screen.getByText(/linking google contacts/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(contactService.connectGoogleContacts).toHaveBeenCalledWith('mock_code_contacts', contactsState)
      expect(screen.getByText(/connected successfully/i)).toBeInTheDocument()
    })
  })

  it('routes gmail OAuth callback to connectGmail and navigates to chat', async () => {
    const gmailState = makeMockState('gmail')
    gmailService.connectGmail.mockResolvedValueOnce({
      connected: true,
      email: 'user@gmail.com',
      unread_notifications_count: 0,
    })

    render(
      <MemoryRouter initialEntries={[`/auth/google/callback?code=mock_code_gmail&state=${gmailState}`]}>
        <AuthProvider>
          <GoogleCallbackPage />
        </AuthProvider>
      </MemoryRouter>
    )

    expect(screen.getByText(/linking gmail notifications/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(gmailService.connectGmail).toHaveBeenCalledWith('mock_code_gmail', gmailState)
      expect(screen.getByText(/connected successfully/i)).toBeInTheDocument()
    })
  })

  it('handles contacts permission denial with friendly message and Return to Chat', async () => {
    const contactsState = makeMockState('contacts')

    render(
      <MemoryRouter initialEntries={[`/auth/google/callback?error=access_denied&state=${contactsState}`]}>
        <AuthProvider>
          <GoogleCallbackPage />
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText(/integration cancelled or failed/i)).toBeInTheDocument()
      expect(screen.getByText(/google contacts access was not granted/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /return to chat/i })).toBeInTheDocument()
    })
  })

  it('handles gmail permission denial with friendly message and Return to Chat', async () => {
    const gmailState = makeMockState('gmail')

    render(
      <MemoryRouter initialEntries={[`/auth/google/callback?error=access_denied&state=${gmailState}`]}>
        <AuthProvider>
          <GoogleCallbackPage />
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText(/integration cancelled or failed/i)).toBeInTheDocument()
      expect(screen.getByText(/gmail notification access was not granted/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /return to chat/i })).toBeInTheDocument()
    })
  })

  it('renders IntegrationsDialog showing only Gmail status, with Contacts Discovery removed', async () => {
    gmailService.getStatus.mockResolvedValueOnce({
      connected: false,
    })

    render(
      <IntegrationsDialog isOpen={true} onClose={vi.fn()} />
    )

    await waitFor(() => {
      expect(screen.getByText('Gmail Inbox Notifications')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /connect gmail notifications/i })).toBeInTheDocument()
    })

    expect(screen.queryByText('Google Contacts Discovery')).not.toBeInTheDocument()
    expect(screen.queryByText(/sync contacts/i)).not.toBeInTheDocument()
    expect(contactService.getGoogleStatus).not.toHaveBeenCalled()
  })

  it('disconnects Gmail independently from the panel with only one disconnect action', async () => {
    window.confirm = vi.fn().mockReturnValue(true)
    gmailService.getStatus.mockResolvedValueOnce({
      connected: true,
      email: 'user@gmail.com',
      unread_notifications_count: 1,
    })
    gmailService.disconnect.mockResolvedValueOnce({ message: 'Disconnected' })

    render(
      <IntegrationsDialog isOpen={true} onClose={vi.fn()} />
    )

    await waitFor(() => {
      expect(screen.getAllByRole('button', { name: /disconnect/i }).length).toBe(1)
    })

    fireEvent.click(screen.getByRole('button', { name: /disconnect/i }))

    await waitFor(() => {
      expect(gmailService.disconnect).toHaveBeenCalled()
      expect(contactService.disconnectGoogle).not.toHaveBeenCalled()
    })
  })

  it('renders GmailNotificationsPopover and marks notification as read', async () => {
    gmailService.getStatus.mockResolvedValueOnce({
      connected: true,
      email: 'work@company.com',
    })
    gmailService.getNotifications.mockResolvedValueOnce({
      unread_count: 1,
      total_count: 1,
      notifications: [
        {
          id: 'notif-1',
          sender: 'boss@company.com',
          subject: 'Urgent: Project Update',
          snippet: 'Please check the latest radar report...',
          is_read: false,
          created_at: '2026-10-24T15:00:00Z',
        },
      ],
    })
    gmailService.markAsRead.mockResolvedValueOnce({ message: 'Marked as read' })

    render(
      <GmailNotificationsPopover isOpen={true} onClose={vi.fn()} onOpenSettings={vi.fn()} />
    )

    await waitFor(() => {
      expect(screen.getByText('Urgent: Project Update')).toBeInTheDocument()
      expect(screen.getByText('boss@company.com')).toBeInTheDocument()
      expect(screen.getByText(/1 unread/i)).toBeInTheDocument()
    })

    // Click notification item to mark read
    fireEvent.click(screen.getByText('Urgent: Project Update'))

    await waitFor(() => {
      expect(gmailService.markAsRead).toHaveBeenCalledWith('notif-1')
    })
  })
})
