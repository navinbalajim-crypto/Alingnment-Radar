import React, { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { invitationService } from '../../services/invitationService'
import { useAuth } from '../../context/AuthContext'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { VerifyEmailCode } from '../auth/VerifyEmailCode'
import { ChooseUsername } from '../auth/ChooseUsername'
import { Users, Mail, Compass, AlertCircle, Calendar } from 'lucide-react'
import { formatFullDateTime } from '../../utils/date'

export function JoinGroupPage() {
  const { token } = useParams()
  const navigate = useNavigate()
  const { handleAuthSuccess } = useAuth()

  const [preview, setPreview] = useState(null)
  const [step, setStep] = useState('preview') // 'preview' | 'code' | 'username'
  const [email, setEmail] = useState('')
  const [registrationTicket, setRegistrationTicket] = useState('')
  const [cooldownSeconds, setCooldownSeconds] = useState(60)

  const [isLoading, setIsLoading] = useState(true)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState(null)

  // Load invitation preview
  useEffect(() => {
    const fetchPreview = async () => {
      try {
        const data = await invitationService.previewInvitation(token)
        setPreview(data)
      } catch (err) {
        setError(err.response?.data?.message || err.response?.data?.detail || 'This invitation link is invalid or has expired.')
      } finally {
        setIsLoading(false)
      }
    }

    if (token) {
      fetchPreview()
    }
  }, [token])

  // Request code
  const handleRequestCode = async (e) => {
    e.preventDefault()
    if (!email.trim()) return

    setIsSubmitting(true)
    setError(null)
    try {
      const res = await invitationService.requestCode(token, email.trim().toLowerCase())
      setCooldownSeconds(res.cooldown_seconds || 60)
      setStep('code')
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to request invitation code.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Resend code
  const handleResendCode = async () => {
    setError(null)
    try {
      const res = await invitationService.requestCode(token, email.trim().toLowerCase())
      setCooldownSeconds(res.cooldown_seconds || 60)
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to resend code.')
    }
  }

  // Verify code
  const handleVerifyCode = async (code) => {
    setIsSubmitting(true)
    setError(null)
    try {
      const res = await invitationService.verifyCode(token, email.trim().toLowerCase(), code)
      if (res.is_existing_user && res.tokens) {
        // Existing user: logged in and joined group!
        handleAuthSuccess(res.tokens.user, res.tokens.access_token)
        navigate('/chat', { replace: true })
      } else if (res.registration_ticket) {
        // New user: proceed to pick username
        setRegistrationTicket(res.registration_ticket)
        setStep('username')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Invalid or expired code.')
    } finally {
      setIsSubmitting(false)
    }
  }

  // Complete registration for new user
  const handleCompleteRegistration = async ({ username, displayName }) => {
    setIsSubmitting(true)
    setError(null)
    try {
      const res = await invitationService.completeRegistration(
        token,
        registrationTicket,
        username,
        displayName
      )
      handleAuthSuccess(res.user, res.access_token)
      navigate('/chat', { replace: true })
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to finish registration.')
    } finally {
      setIsSubmitting(false)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-[#F2F2F7] dark:bg-neutral-950">
        <div className="animate-pulse flex flex-col items-center">
          <div className="w-12 h-12 rounded-2xl bg-neutral-300 dark:bg-neutral-800 mb-4" />
          <p className="text-sm text-neutral-500">Checking invitation details...</p>
        </div>
      </div>
    )
  }

  if (error && !preview) {
    return (
      <div className="min-h-screen flex items-center justify-center p-4 bg-[#F2F2F7] dark:bg-neutral-950">
        <div className="w-full max-w-md bg-white dark:bg-neutral-900 rounded-3xl shadow-apple border border-black/[0.06] dark:border-white/[0.08] p-8 text-center">
          <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-950/60 text-red-600 flex items-center justify-center mx-auto mb-4">
            <AlertCircle className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
            Invitation Expired or Invalid
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-2 mb-6">
            {error}
          </p>
          <Link to="/login">
            <Button variant="primary" className="w-full">
              Go to Sign In
            </Button>
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#F2F2F7] dark:bg-neutral-950">
      <div className="w-full max-w-md bg-white dark:bg-neutral-900 rounded-3xl shadow-apple border border-black/[0.06] dark:border-white/[0.08] p-8 transition-all">
        {/* Brand Header */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <div className="w-8 h-8 rounded-xl bg-neutral-900 dark:bg-white flex items-center justify-center text-white dark:text-neutral-900 shadow-subtle">
            <Compass className="w-4 h-4" />
          </div>
          <span className="text-sm font-bold tracking-tight text-neutral-900 dark:text-white">
            Alignment Radar
          </span>
        </div>

        {/* Group Preview Card */}
        {preview && (
          <div className="p-4 rounded-2xl bg-neutral-50 dark:bg-neutral-800/60 border border-neutral-100 dark:border-neutral-800 mb-6 text-center">
            <div className="w-14 h-14 rounded-2xl bg-blue-50 dark:bg-blue-950/60 text-apple-blue flex items-center justify-center mx-auto mb-3">
              <Users className="w-7 h-7" />
            </div>
            <h2 className="text-lg font-bold text-neutral-900 dark:text-neutral-100">
              {preview.group_title}
            </h2>
            <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
              Invited by <span className="font-semibold text-neutral-700 dark:text-neutral-200">@{preview.invited_by_username}</span>
            </p>
            {preview.expires_at && (
              <div className="flex items-center justify-center gap-1 text-[11px] text-neutral-400 mt-2">
                <Calendar className="w-3 h-3" />
                <span>Expires {formatFullDateTime(preview.expires_at)}</span>
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="p-3 mb-4 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl">
            {error}
          </div>
        )}

        {/* Steps */}
        {step === 'preview' && (
          <form onSubmit={handleRequestCode} className="flex flex-col gap-4">
            <p className="text-xs text-neutral-600 dark:text-neutral-400 text-center">
              Enter your email to receive a secure join code. Both existing members and new teammates can join seamlessly.
            </p>
            <Input
              label="Email Address"
              type="email"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              disabled={isSubmitting}
              icon={Mail}
              autoFocus
            />
            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isSubmitting}
              className="w-full mt-1"
            >
              Get Join Code
            </Button>
          </form>
        )}

        {step === 'code' && (
          <VerifyEmailCode
            email={email}
            initialCooldown={cooldownSeconds}
            onVerify={handleVerifyCode}
            onResend={handleResendCode}
            onBack={() => setStep('preview')}
            isLoading={isSubmitting}
            error={error}
          />
        )}

        {step === 'username' && (
          <ChooseUsername
            email={email}
            onComplete={handleCompleteRegistration}
            isLoading={isSubmitting}
            error={error}
          />
        )}
      </div>
    </div>
  )
}
