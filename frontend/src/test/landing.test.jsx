import React from 'react'
import { render, screen } from '@testing-library/react'
import { MemoryRouter, Routes, Route, Navigate } from 'react-router-dom'
import { describe, it, expect } from 'vitest'
import { LandingPage } from '../components/landing/LandingPage'

function renderLanding() {
  return render(
    <MemoryRouter>
      <LandingPage />
    </MemoryRouter>
  )
}

describe('Landing page', () => {
  it('opens with the story headline inside the scoped landing root', () => {
    const { container } = renderLanding()
    expect(container.querySelector('.alignment-landing')).toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 1, name: /most misunderstandings start with a message that seemed clear/i })
    ).toBeInTheDocument()
  })

  it('presents each of the eight features', () => {
    renderLanding()
    for (const title of [
      'More than just chat.',
      'AI that helps you stay aligned.',
      'Your AI requests, routed sensibly.',
      'Speak. Be heard.',
      'Meet without leaving the chat.',
      'Relevant, right in the conversation.',
      'Stronger together.',
      'Clear about how your data is protected.',
    ]) {
      // Rendered once for the sticky desktop monitor and once for the stacked phone layout.
      expect(screen.getAllByRole('heading', { level: 2, name: title }).length).toBeGreaterThan(0)
    }
  })

  it('closes with links to the existing auth routes', () => {
    renderLanding()
    expect(screen.getByRole('heading', { name: 'Better conversations start with better understanding.' })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /create your account/i })).toHaveAttribute('href', '/register')
    const signIns = screen.getAllByRole('link', { name: /^sign in$/i })
    expect(signIns.length).toBeGreaterThan(0)
    signIns.forEach((a) => expect(a).toHaveAttribute('href', '/login'))
    expect(screen.getByRole('link', { name: /^create account$/i })).toHaveAttribute('href', '/register')
  })

  it('does not reuse the excluded collage panels or make unsupported claims', () => {
    const { container } = renderLanding()
    const text = container.textContent
    expect(text).not.toMatch(/Anywhere\. Anytime\./)
    expect(text).not.toMatch(/A more aligned tomorrow/)
    expect(text).not.toMatch(/Chat\s*•\s*Align\s*•\s*Achieve/)
    expect(text).not.toMatch(/end-to-end/i)
  })

  it('tells the phone story as text and plays the features on the monitor (desktop)', () => {
    const original = window.matchMedia
    window.matchMedia = (query) => ({
      matches: query.includes('min-width'),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })
    let container
    try {
      ;({ container } = renderLanding())
    } finally {
      window.matchMedia = original
    }
    expect(screen.getByText(/chatting with Arjun on her phone/i)).toBeInTheDocument()
    expect(screen.getByText(/“The usual one\.”/)).toBeInTheDocument()
    expect(screen.getByTestId('phone-chat-panel')).toBeInTheDocument()
    const monitor = screen.getByTestId('monitor-features')
    expect(monitor).toHaveTextContent('More than just chat.')
    expect(monitor).toHaveTextContent('Clear about how your data is protected.')
    // One continuous pinned scene: no separate stacked feature section on desktop.
    expect(container.querySelector('section[aria-label="Features"]')).toBeNull()
  })

  it('with reduced motion: a short static scene, every feature as stacked screens, links reachable', () => {
    const original = window.matchMedia
    window.matchMedia = (query) => ({
      matches: query.includes('prefers-reduced-motion') || query.includes('min-width'),
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })
    try {
      const { container } = renderLanding()
      const scene = container.querySelector('section[aria-label^="Story"]')
      expect(scene.style.height).toBe('100svh')
      expect(screen.queryByTestId('monitor-features')).toBeNull()
      const stacked = container.querySelector('section[aria-label="Features"]')
      expect(stacked).not.toBeNull()
      expect(stacked.querySelectorAll('h2')).toHaveLength(8)
      expect(screen.getByRole('link', { name: /create your account/i })).toHaveAttribute('href', '/register')
    } finally {
      window.matchMedia = original
    }
  })

  it('keeps signed-in users going straight to /chat from /', () => {
    // Mirrors router.jsx: "/" is wrapped in PublicAuthRoute, which redirects authenticated users.
    const PublicAuthRoute = ({ isAuthenticated, children }) =>
      isAuthenticated ? <Navigate to="/chat" replace /> : children
    render(
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<PublicAuthRoute isAuthenticated><LandingPage /></PublicAuthRoute>} />
          <Route path="/chat" element={<p>chat app</p>} />
        </Routes>
      </MemoryRouter>
    )
    expect(screen.getByText('chat app')).toBeInTheDocument()
  })
})
