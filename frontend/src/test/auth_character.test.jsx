import React from 'react'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, it, expect, vi } from 'vitest'
import { InteractiveAuthCharacter } from '../components/auth/InteractiveAuthCharacter'
import { ChooseUsername } from '../components/auth/ChooseUsername'
import { LoginPage } from '../components/auth/LoginPage'
import { RegisterPage } from '../components/auth/RegisterPage'

vi.mock('../services/authService', () => ({
  authService: {
    checkUsernameAvailability: vi.fn().mockResolvedValue({ available: true, message: 'ok' }),
  },
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({ handleAuthSuccess: vi.fn() }),
}))

const eyes = () => screen.getAllByTestId('auth-character-eye')
const transforms = () => eyes().map((e) => e.style.transform)
const settle = () => new Promise((r) => setTimeout(r, 5))

function renderSignupStep() {
  return render(
    <div>
      <InteractiveAuthCharacter />
      <ChooseUsername email="a@b.com" onComplete={vi.fn()} />
    </div>
  )
}

describe('InteractiveAuthCharacter', () => {
  it('is decorative: hidden from assistive tech and never intercepts pointer input', () => {
    renderSignupStep()
    const root = screen.getByTestId('auth-character')
    expect(root).toHaveAttribute('aria-hidden', 'true')
    expect(root.getAttribute('class')).toContain('pointer-events-none')
    expect(eyes()).toHaveLength(2)
  })

  it('looks toward the username field on focus and keeps tracking while typing', () => {
    renderSignupStep()
    const username = screen.getByPlaceholderText('e.g. alex_chen')
    act(() => username.focus())
    expect(transforms().every((t) => t.startsWith('translate('))).toBe(true)
    expect(transforms().some((t) => t.includes('scaleY'))).toBe(false)

    fireEvent.change(username, { target: { value: 'alex' } })
    fireEvent.input(username)
    expect(transforms().every((t) => t.startsWith('translate('))).toBe(true)
  })

  it('blushes and looks away when a password field is focused, regardless of what is typed or where the mouse is', () => {
    renderSignupStep()
    const blush = screen.getByTestId('auth-character-blush')
    expect(blush.style.opacity).not.toBe('1')

    const password = screen.getByPlaceholderText('Min 8 characters with letter & number')
    act(() => password.focus())
    const shy = transforms()
    expect(blush.style.opacity).toBe('1')
    expect(shy.every((t) => t.includes('translate(-75%, -32%)'))).toBe(true)

    // No reaction to password content/length, and the mouse can't pull the eyes back.
    fireEvent.change(password, { target: { value: 'hunter2hunter2' } })
    fireEvent.input(password)
    fireEvent.pointerMove(window, { clientX: 900, clientY: 900 })
    expect(transforms()).toEqual(shy)

    const confirm = screen.getByPlaceholderText('Re-enter your password')
    act(() => confirm.focus())
    expect(blush.style.opacity).toBe('1')
  })

  it('stops blushing and returns to rest when focus leaves the form', async () => {
    renderSignupStep()
    const password = screen.getByPlaceholderText('Min 8 characters with letter & number')
    act(() => password.focus())
    await act(async () => {
      password.blur()
      await settle()
    })
    expect(transforms()).toEqual(['', ''])
    expect(screen.getByTestId('auth-character-blush').style.opacity).toBe('0')
  })

  it('keeps the password pose locked when the browser window loses focus and the mouse moves over the page', async () => {
    renderSignupStep()
    const password = screen.getByPlaceholderText('Min 8 characters with letter & number')
    act(() => password.focus())
    const shy = transforms()

    // Window blur: a focusout fires, but the password field is still the active element.
    await act(async () => {
      password.dispatchEvent(new FocusEvent('focusout', { bubbles: true }))
      await settle()
      fireEvent.pointerMove(window, { clientX: 5, clientY: 5 })
      await new Promise((r) => requestAnimationFrame(r))
    })
    expect(document.activeElement).toBe(password)
    expect(transforms()).toEqual(shy)
    expect(screen.getByTestId('auth-character-blush').style.opacity).toBe('1')
  })

  it('switches directly from username to password without passing through mouse tracking', async () => {
    renderSignupStep()
    const username = screen.getByPlaceholderText('e.g. alex_chen')
    const password = screen.getByPlaceholderText('Min 8 characters with letter & number')
    act(() => username.focus())

    const seen = []
    const eye = eyes()[0]
    const observer = new MutationObserver(() => seen.push(eye.style.transform))
    observer.observe(eye, { attributes: true, attributeFilter: ['style'] })
    await act(async () => {
      password.focus()
      await settle()
    })
    observer.disconnect()

    expect(seen).not.toContain('') // never reset to the idle/mouse pose in between
    expect(transforms().every((t) => t.includes('translate(-75%, -32%)'))).toBe(true)
  })

  it('follows the mouse when no field is focused, but not while watching the username field', async () => {
    renderSignupStep()
    await act(async () => {
      fireEvent.pointerMove(window, { clientX: 800, clientY: 10 })
      await new Promise((r) => requestAnimationFrame(r))
    })
    expect(transforms().every((t) => t.startsWith('translate('))).toBe(true)

    const username = screen.getByPlaceholderText('e.g. alex_chen')
    act(() => username.focus())
    const watching = transforms()
    await act(async () => {
      fireEvent.pointerMove(window, { clientX: 0, clientY: 0 })
      await new Promise((r) => requestAnimationFrame(r))
    })
    expect(transforms()).toEqual(watching)
  })

  it('appears on both the Sign In and Create Account pages', () => {
    const { unmount } = render(<MemoryRouter><LoginPage /></MemoryRouter>)
    expect(screen.getByTestId('auth-character')).toBeInTheDocument()
    unmount()
    render(<MemoryRouter><RegisterPage /></MemoryRouter>)
    expect(screen.getByTestId('auth-character')).toBeInTheDocument()
  })
})

describe('Account navigation links', () => {
  it('Sign In links to the existing /register route, directly under the Sign In button', () => {
    render(<MemoryRouter><LoginPage /></MemoryRouter>)
    const link = screen.getByRole('link', { name: 'Create an account' })
    expect(link).toHaveAttribute('href', '/register')
    expect(link.closest('p')).toHaveTextContent('New to Alignment Radar? Create an account')
    const signInButton = screen.getByRole('button', { name: 'Sign In' })
    expect(signInButton.nextElementSibling).toBe(link.closest('p'))
    expect(screen.getAllByRole('link', { name: /create an account/i })).toHaveLength(1)
  })

  it('Create Account links to the existing /login route, directly under its primary button', () => {
    render(<MemoryRouter><RegisterPage /></MemoryRouter>)
    const link = screen.getByRole('link', { name: 'Sign in' })
    expect(link).toHaveAttribute('href', '/login')
    expect(link.closest('p')).toHaveTextContent('Already have an account? Sign in')
    const continueButton = screen.getByRole('button', { name: 'Continue with Email' })
    expect(continueButton.nextElementSibling).toBe(link.closest('p'))
    expect(screen.getAllByRole('link', { name: 'Sign in' })).toHaveLength(1)
  })
})
