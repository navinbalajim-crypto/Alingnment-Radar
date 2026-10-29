import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BrowserRouter, MemoryRouter } from 'react-router-dom'
import { GoogleButton } from '../components/ui/GoogleButton'
import { GoogleCallbackPage } from '../components/auth/GoogleCallbackPage'
import { UserSearchDialog } from '../components/layout/UserSearchDialog'
import { AuthProvider } from '../context/AuthContext'
import { ChatProvider } from '../context/ChatContext'
import { authService } from '../services/authService'
import { contactService } from '../services/contactService'

vi.mock('../services/authService', () => ({
  authService: {
    getGoogleAuthUrl: vi.fn(),
    loginWithGoogle: vi.fn(),
    searchUsers: vi.fn(),
  },
}))

vi.mock('../services/contactService', () => ({
  contactService: {
    getGoogleStatus: vi.fn(),
    getContacts: vi.fn(),
    syncGoogleContacts: vi.fn(),
    disconnectGoogle: vi.fn(),
  },
}))

describe('Google OAuth and Google Contacts Frontend', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders GoogleButton and initiates authorization flow on click', async () => {
    authService.getGoogleAuthUrl.mockResolvedValueOnce({
      url: 'https://accounts.google.com/o/oauth2/v2/auth?mock=1',
      state: 'state123',
    })

    const deleteWindowLocation = () => {
      delete window.location
      window.location = { href: '', origin: 'http://localhost:5173' }
    }
    deleteWindowLocation()

    render(
      <GoogleButton label="Continue with Google" />
    )

    const btn = screen.getByRole('button', { name: /continue with google/i })
    expect(btn).toBeInTheDocument()

    fireEvent.click(btn)

    await waitFor(() => {
      expect(authService.getGoogleAuthUrl).toHaveBeenCalled()
      expect(window.location.href).toBe('https://accounts.google.com/o/oauth2/v2/auth?mock=1')
    })
  })

  it('renders GoogleCallbackPage, exchanges code, and saves session', async () => {
    authService.loginWithGoogle.mockImplementation(async (code) => {
      localStorage.setItem('ar_access_token', 'jwt-access-google')
      return {
        access_token: 'jwt-access-google',
        refresh_token: 'refresh-google',
        user: {
          id: 'user-google-1',
          email: 'alice@google.com',
          username: 'alice_google',
          display_name: 'Alice Google',
        },
      }
    })

    render(
      <MemoryRouter initialEntries={['/auth/google/callback?code=mock_code_123']}>
        <AuthProvider>
          <GoogleCallbackPage />
        </AuthProvider>
      </MemoryRouter>
    )

    expect(screen.getByText(/authenticating with google/i)).toBeInTheDocument()

    await waitFor(() => {
      expect(authService.loginWithGoogle).toHaveBeenCalledWith('mock_code_123', null)
      expect(localStorage.getItem('ar_access_token')).toBe('jwt-access-google')
    })
  })

  it('renders GoogleCallbackPage error when access is denied', async () => {
    render(
      <MemoryRouter initialEntries={['/auth/google/callback?error=access_denied']}>
        <AuthProvider>
          <GoogleCallbackPage />
        </AuthProvider>
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByText(/authentication failed/i)).toBeInTheDocument()
      expect(screen.getByText(/google sign-in was cancelled/i)).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /return to sign in/i })).toBeInTheDocument()
    })
  })

  it('renders Google Contacts in UserSearchDialog and displays On Radar badge for teammates', async () => {
    contactService.getGoogleStatus.mockResolvedValueOnce({
      connected: true,
      email: 'me@company.com',
      has_contacts_scope: true,
    })

    contactService.getContacts.mockResolvedValueOnce({
      total: 2,
      contacts: [
        {
          id: 'c-1',
          contact_email: 'teammate@company.com',
          contact_name: 'Marcus Teammate',
          is_registered: true,
          registered_username: 'marcus',
          registered_user_id: 'user-marcus',
        },
        {
          id: 'c-2',
          contact_email: 'client@external.com',
          contact_name: 'External Client',
          is_registered: false,
          registered_username: null,
          registered_user_id: null,
        },
      ],
    })

    render(
      <BrowserRouter>
        <AuthProvider>
          <ChatProvider>
            <UserSearchDialog isOpen={true} onClose={vi.fn()} />
          </ChatProvider>
        </AuthProvider>
      </BrowserRouter>
    )

    // Switch to Google Contacts tab
    const contactsTab = screen.getByRole('button', { name: /google contacts/i })
    fireEvent.click(contactsTab)

    await waitFor(() => {
      expect(contactService.getContacts).toHaveBeenCalled()
      expect(screen.getByText('Marcus Teammate')).toBeInTheDocument()
      expect(screen.getByText(/on radar/i)).toBeInTheDocument()
      expect(screen.getByText('External Client')).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /chat/i })).toBeInTheDocument()
      expect(screen.getByRole('button', { name: /invite/i })).toBeInTheDocument()
    })
  })
})
