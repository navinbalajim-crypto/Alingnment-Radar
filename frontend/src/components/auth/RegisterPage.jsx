import React, { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { GoogleButton } from '../ui/GoogleButton'
import { VerifyEmailCode } from './VerifyEmailCode'
import { ChooseUsername } from './ChooseUsername'
import { AuthLayout, OrDivider } from './AuthLayout'
import { authService } from '../../services/authService'
import { useAuth } from '../../context/AuthContext'
import { Mail, ShieldCheck, LogIn } from 'lucide-react'

export function RegisterPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { handleAuthSuccess } = useAuth()

  // Step state: 'email' | 'code' | 'username'
  const [step, setStep] = useState('email')
  const [email, setEmail] = useState(searchParams.get('email') || '')
  const [registrationTicket, setRegistrationTicket] = useState('')
  const [cooldownSeconds, setCooldownSeconds] = useState(60)

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  // Step 1: Request code
  const handleRequestCode = async (e) => {
    e.preventDefault()
    if (!email.trim()) return

    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.requestRegisterCode(email.trim().toLowerCase())
      setCooldownSeconds(res.cooldown_seconds || 60)
      setStep('code')
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || 'Failed to send verification code. Please check your email.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  // Resend code handler
  const handleResendCode = async () => {
    setError(null)
    try {
      const res = await authService.requestRegisterCode(email.trim().toLowerCase())
      setCooldownSeconds(res.cooldown_seconds || 60)
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || 'Failed to resend code.'
      setError(msg)
    }
  }

  // Step 2: Verify code
  const handleVerifyCode = async (code) => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.verifyRegisterCode(email.trim().toLowerCase(), code)
      setRegistrationTicket(res.registration_ticket)
      setStep('username')
    } catch (err) {
      const msg = err.response?.data?.detail || 'Invalid or expired verification code.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  // Step 3: Complete registration
  const handleCompleteRegistration = async ({ username, displayName, password }) => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.completeRegistration(
        registrationTicket,
        username,
        displayName,
        password
      )
      handleAuthSuccess(res.user, res.access_token)
      navigate('/chat', { replace: true })
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || 'Failed to complete registration.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthLayout>
        {/* Auth Mode Switcher */}
        {step === 'email' && (
          <div className="flex p-1 bg-neutral-100 dark:bg-neutral-800 rounded-2xl mb-6">
            <button
              type="button"
              onClick={() => navigate(`/login${email ? `?email=${encodeURIComponent(email)}` : ''}`)}
              className="flex-1 py-2 text-xs font-medium rounded-xl text-neutral-500 hover:text-neutral-900 dark:hover:text-white transition-all"
            >
              Sign In
            </button>
            <button
              type="button"
              className="flex-1 py-2 text-xs font-semibold rounded-xl bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-subtle transition-all"
            >
              Create Account
            </button>
          </div>
        )}

        {/* Form Steps */}
        {step === 'email' && (
          <form onSubmit={handleRequestCode} className="flex flex-col gap-5">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
                Create your account
              </h1>
              <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">
                Join Alignment Radar and start building better conversations. We'll email you a code to verify it's you.
              </p>
            </div>

            {error && (
              <div className="p-3.5 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl flex flex-col gap-2">
                <div>{error}</div>
                {error.toLowerCase().includes('sign in') && (
                  <button
                    type="button"
                    onClick={() => navigate(`/login?email=${encodeURIComponent(email)}`)}
                    className="self-start text-xs font-semibold text-apple-blue dark:text-blue-400 hover:underline flex items-center gap-1.5 pt-1 border-t border-red-200/60 dark:border-red-800/60 w-full"
                  >
                    <LogIn className="w-3.5 h-3.5" />
                    Already registered? Sign in with {email || 'this email'} →
                  </button>
                )}
              </div>
            )}

            <GoogleButton label="Sign up with Google" onError={(err) => setError(err)} />

            <OrDivider label="or with email" />

            <Input
              label="Email Address"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isLoading}
              icon={Mail}
              autoFocus
            />

            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              className="w-full mt-2"
            >
              Continue with Email
            </Button>

            <p className="text-center text-xs text-neutral-500 dark:text-neutral-400 -mt-1">
              Already have an account?{' '}
              <Link to="/login" className="font-semibold text-apple-blue dark:text-blue-400 hover:underline">
                Sign in
              </Link>
            </p>

            <div className="flex items-center justify-center gap-1.5 text-xs text-neutral-500">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
              <span>No password needed • One-time 6-digit email code</span>
            </div>
          </form>
        )}

        {step === 'code' && (
          <VerifyEmailCode
            email={email}
            initialCooldown={cooldownSeconds}
            onVerify={handleVerifyCode}
            onResend={handleResendCode}
            onBack={() => setStep('email')}
            isLoading={isLoading}
            error={error}
          />
        )}

        {step === 'username' && (
          <ChooseUsername
            email={email}
            onComplete={handleCompleteRegistration}
            isLoading={isLoading}
            error={error}
          />
        )}
    </AuthLayout>
  )
}
