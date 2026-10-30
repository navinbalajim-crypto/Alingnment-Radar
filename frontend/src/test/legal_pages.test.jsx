import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { PrivacyPolicyPage } from '../components/legal/PrivacyPolicyPage'
import { TermsOfServicePage } from '../components/legal/TermsOfServicePage'

describe('Legal Pages', () => {
  it('renders Privacy Policy page with Google Limited Use and AI disclosures', () => {
    render(
      <MemoryRouter initialEntries={['/privacy']}>
        <PrivacyPolicyPage />
      </MemoryRouter>
    )

    // Heading & Title
    expect(screen.getByRole('heading', { level: 1, name: /privacy policy/i })).toBeInTheDocument()

    // Core sections
    expect(screen.getByText(/Google Account Information/i)).toBeInTheDocument()
    expect(screen.getByText(/Google API Services User Data Policy Compliance/i)).toBeInTheDocument()
    expect(screen.getByText(/Speech-to-Text Transcription/i)).toBeInTheDocument()
    expect(screen.getByText(/AI Processing & Third-Party Providers/i)).toBeInTheDocument()
    expect(screen.getByText(/privacy@alignmentradar.com/i)).toBeInTheDocument()
  })

  it('renders Terms of Service page with acceptable use, AI disclaimer, and ownership', () => {
    render(
      <MemoryRouter initialEntries={['/terms']}>
        <TermsOfServicePage />
      </MemoryRouter>
    )

    // Heading & Title
    expect(screen.getByRole('heading', { level: 1, name: /terms of service/i })).toBeInTheDocument()

    // Core sections
    expect(screen.getByText(/Welcome to Alignment Radar/i)).toBeInTheDocument()
    expect(screen.getByText(/Acceptable Use Policy/i)).toBeInTheDocument()
    expect(screen.getByText(/AI Features & Assistive Disclaimer/i)).toBeInTheDocument()
    expect(screen.getByText(/Content Ownership & License/i)).toBeInTheDocument()
    expect(screen.getByText(/terms@alignmentradar.com/i)).toBeInTheDocument()
  })
})

