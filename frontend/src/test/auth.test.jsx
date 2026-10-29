import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { BrowserRouter } from 'react-router-dom'
import { VerifyEmailCode } from '../components/auth/VerifyEmailCode'
import { ChooseUsername } from '../components/auth/ChooseUsername'
import { LoginPage } from '../components/auth/LoginPage'
import { AuthProvider } from '../context/AuthContext'
import { authService } from '../services/authService'

vi.mock('../services/authService', () => ({
  authService: {
    loginWithPassword: vi.fn(),
    requestLoginCode: vi.fn(),
    verifyLoginCode: vi.fn(),
    checkUsernameAvailability: vi.fn(),
    requestRegisterCode: vi.fn(),
    verifyRegisterCode: vi.fn(),
    completeRegistration: vi.fn(),
    getCurrentUser: vi.fn(),
    logout: vi.fn(),
  },
}))

describe('Auth Flow Components', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
  })

  it('renders VerifyEmailCode and allows 6-digit input', async () => {
    const onVerify = vi.fn()
    render(
      <VerifyEmailCode
        email="test@example.com"
        onVerify={onVerify}
        initialCooldown={60}
      />
    )

    expect(screen.getByText(/check your email/i)).toBeInTheDocument()
    expect(screen.getByText(/test@example.com/i)).toBeInTheDocument()

    const inputs = screen.getAllByRole('textbox')
    expect(inputs).toHaveLength(6)

    fireEvent.change(inputs[0], { target: { value: '1' } })
    fireEvent.change(inputs[1], { target: { value: '2' } })
    fireEvent.change(inputs[2], { target: { value: '3' } })
    fireEvent.change(inputs[3], { target: { value: '4' } })
    fireEvent.change(inputs[4], { target: { value: '5' } })
    fireEvent.change(inputs[5], { target: { value: '6' } })

    const verifyButton = screen.getByRole('button', { name: /verify code/i })
    expect(verifyButton).not.toBeDisabled()

    fireEvent.click(verifyButton)
    expect(onVerify).toHaveBeenCalledWith('123456')
  })

  it('validates username availability in ChooseUsername component', async () => {
    authService.checkUsernameAvailability.mockResolvedValueOnce({
      username: 'sam_altman',
      available: true,
      message: 'Username is available',
    })

    const onComplete = vi.fn()
    render(
      <ChooseUsername
        email="sam@openai.com"
        onComplete={onComplete}
      />
    )

    const usernameInput = screen.getByLabelText(/username/i)
    fireEvent.change(usernameInput, { target: { value: 'sam_altman' } })

    await waitFor(
      () => {
        expect(authService.checkUsernameAvailability).toHaveBeenCalledWith('sam_altman')
        expect(screen.getByText('Username is available')).toBeInTheDocument()
      },
      { timeout: 2500 }
    )

    const submitBtn = screen.getByRole('button', { name: /complete registration/i })
    expect(submitBtn).not.toBeDisabled()
    fireEvent.click(submitBtn)

    expect(onComplete).toHaveBeenCalledWith({
      username: 'sam_altman',
      displayName: undefined,
    })
  })

  it('handles username and password login submission', async () => {
    authService.loginWithPassword.mockResolvedValueOnce({
      access_token: 'fake-jwt-token',
      token_type: 'bearer',
      user: { id: 'usr-123', username: 'testuser', email: 'test@example.com' },
    })

    render(
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    )

    const usernameInput = screen.getByLabelText(/^username$/i)
    const passwordInput = screen.getByLabelText(/^password$/i)
    fireEvent.change(usernameInput, { target: { value: 'testuser' } })
    fireEvent.change(passwordInput, { target: { value: 'ValidPass123' } })

    const signInBtn = screen.getByRole('button', { name: /^sign in$/i })
    fireEvent.click(signInBtn)

    await waitFor(() => {
      expect(authService.loginWithPassword).toHaveBeenCalledWith('testuser', 'ValidPass123')
    })
  })

  it('handles login code request submission via email login toggle', async () => {
    authService.requestLoginCode.mockResolvedValueOnce({
      message: 'Verification code sent',
      email: 'alex@example.com',
      cooldown_seconds: 60,
    })

    render(
      <BrowserRouter>
        <AuthProvider>
          <LoginPage />
        </AuthProvider>
      </BrowserRouter>
    )

    const toggleBtn = screen.getByRole('button', { name: /continue with email/i })
    fireEvent.click(toggleBtn)

    const emailInput = screen.getByLabelText(/email address/i)
    fireEvent.change(emailInput, { target: { value: 'alex@example.com' } })

    const sendBtn = screen.getByRole('button', { name: /send sign-in code/i })
    fireEvent.click(sendBtn)

    await waitFor(() => {
      expect(authService.requestLoginCode).toHaveBeenCalledWith('alex@example.com')
      expect(screen.getByText(/check your email/i)).toBeInTheDocument()
    })
  })
})
