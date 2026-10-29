import React from 'react'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { RegisterPage } from '../components/auth/RegisterPage'
import { authService } from '../services/authService'

vi.mock('../services/authService', () => ({
  authService: {
    requestRegisterCode: vi.fn().mockResolvedValue({ cooldown_seconds: 60 }),
    verifyRegisterCode: vi.fn().mockResolvedValue({ registration_ticket: 'ticket-123' }),
    checkUsernameAvailability: vi.fn().mockResolvedValue({ available: true, message: 'Username is available' }),
    completeRegistration: vi.fn().mockResolvedValue({ user: { id: 'u1' }, access_token: 'tok' }),
  },
}))

const handleAuthSuccess = vi.fn()
vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ handleAuthSuccess }),
}))

const navigateMock = vi.fn()
vi.mock('react-router-dom', async (orig) => ({
  ...(await orig()),
  useNavigate: () => navigateMock,
}))

// The card and robot must both stay rendered, side by side in the same layout, at every step.
function expectLayoutIntact() {
  expect(screen.getByTestId('auth-character')).toBeInTheDocument()
  expect(screen.getByRole('main')).toBeInTheDocument()
}

describe('Create Account flow inside the redesigned layout', () => {
  it('runs email -> verification code -> username/password -> registration using the existing calls', async () => {
    render(<MemoryRouter><RegisterPage /></MemoryRouter>)
    expectLayoutIntact()

    // Step 1: request a code
    fireEvent.change(screen.getByLabelText(/email address/i), { target: { value: 'New.User@Example.com' } })
    fireEvent.click(screen.getByRole('button', { name: /continue with email/i }))
    await waitFor(() => expect(authService.requestRegisterCode).toHaveBeenCalledWith('new.user@example.com'))

    // Step 2: verification code UI, resend available, then verify
    await screen.findByText(/check your email/i)
    expectLayoutIntact()
    const boxes = screen.getAllByRole('textbox')
    expect(boxes).toHaveLength(6)
    '123456'.split('').forEach((d, i) => fireEvent.change(boxes[i], { target: { value: d } }))
    fireEvent.click(screen.getByRole('button', { name: /verify code/i }))
    await waitFor(() => expect(authService.verifyRegisterCode).toHaveBeenCalledWith('new.user@example.com', '123456'))

    // Step 3: username + password, with the availability check, then complete registration
    const username = await screen.findByLabelText(/username/i)
    expectLayoutIntact()
    fireEvent.change(username, { target: { value: 'new_user' } })
    fireEvent.change(screen.getByPlaceholderText('Min 8 characters with letter & number'), { target: { value: 'abc12345' } })
    fireEvent.change(screen.getByPlaceholderText('Re-enter your password'), { target: { value: 'abc12345' } })
    await waitFor(() => expect(screen.getByText('Username is available')).toBeInTheDocument(), { timeout: 2500 })
    fireEvent.click(screen.getByRole('button', { name: /complete registration/i }))

    await waitFor(() =>
      expect(authService.completeRegistration).toHaveBeenCalledWith('ticket-123', 'new_user', undefined, 'abc12345')
    )
    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith('/chat', { replace: true }))
    expect(handleAuthSuccess).toHaveBeenCalledWith({ id: 'u1' }, 'tok')
  })
})
