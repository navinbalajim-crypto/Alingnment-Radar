import React, { useState } from 'react'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { authService } from '../../services/authService'
import { Mail, KeyRound, Lock, CheckCircle2, X } from 'lucide-react'

export function ForgotPasswordModal({ isOpen, onClose, initialEmail = '' }) {
  const [step, setStep] = useState('email') // 'email' | 'code' | 'password' | 'success'
  const [email, setEmail] = useState(initialEmail)
  const [code, setCode] = useState('')
  const [resetTicket, setResetTicket] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState('')

  if (!isOpen) return null

  const handleRequestReset = async (e) => {
    e.preventDefault()
    if (!email.trim()) return

    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.forgotPassword(email.trim().toLowerCase())
      setSuccessMsg(res.message || 'If an account with that email exists, a verification code has been sent.')
      setStep('code')
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to send reset code.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleVerifyCode = async (e) => {
    e.preventDefault()
    if (!code.trim() || code.length !== 6) {
      setError('Please enter the 6-digit verification code.')
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.verifyResetCode(email.trim().toLowerCase(), code.trim())
      setResetTicket(res.reset_ticket)
      setStep('password')
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Invalid or expired code.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleResetPassword = async (e) => {
    e.preventDefault()
    if (newPassword.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }
    if (!/[A-Za-z]/.test(newPassword) || !/[0-9]/.test(newPassword)) {
      setError('Password must contain at least one letter and one number.')
      return
    }
    if (newPassword !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      await authService.resetPassword(resetTicket, newPassword)
      setStep('success')
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to reset password.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-md bg-white dark:bg-neutral-900 rounded-3xl shadow-apple border border-black/[0.08] dark:border-white/[0.1] p-7 transition-all">
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-1.5 rounded-full text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        {/* Modal Header */}
        <div className="text-center mb-6">
          <div className="mx-auto w-12 h-12 rounded-2xl bg-blue-50 dark:bg-blue-950/60 flex items-center justify-center text-apple-blue mb-3">
            <KeyRound className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-neutral-900 dark:text-white">
            Reset Your Password
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            {step === 'email' && 'Enter your registered email address to receive a recovery code.'}
            {step === 'code' && 'Enter the 6-digit code sent to your email.'}
            {step === 'password' && 'Choose a secure new password for your account.'}
            {step === 'success' && 'Your password has been successfully updated.'}
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl">
            {error}
          </div>
        )}

        {/* Step 1: Email Form */}
        {step === 'email' && (
          <form onSubmit={handleRequestReset} className="flex flex-col gap-4">
            <Input
              label="Registered Email Address"
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
              Send Recovery Code
            </Button>
          </form>
        )}

        {/* Step 2: Code Form */}
        {step === 'code' && (
          <form onSubmit={handleVerifyCode} className="flex flex-col gap-4">
            {successMsg && (
              <p className="text-xs text-emerald-600 dark:text-emerald-400 text-center">
                {successMsg}
              </p>
            )}
            <Input
              label="6-Digit Verification Code"
              type="text"
              placeholder="123456"
              maxLength={6}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^0-9]/g, ''))}
              required
              disabled={isLoading}
              autoFocus
            />
            <Button
              type="submit"
              variant="primary"
              size="lg"
              disabled={code.length !== 6}
              isLoading={isLoading}
              className="w-full mt-2"
            >
              Verify Code
            </Button>
            <button
              type="button"
              onClick={() => { setStep('email'); setError(null) }}
              className="text-xs text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200 text-center transition-colors"
            >
              ← Back to change email
            </button>
          </form>
        )}

        {/* Step 3: New Password Form */}
        {step === 'password' && (
          <form onSubmit={handleResetPassword} className="flex flex-col gap-4">
            <Input
              label="New Password"
              type="password"
              placeholder="At least 8 characters"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              disabled={isLoading}
              icon={Lock}
              autoFocus
            />
            <Input
              label="Confirm New Password"
              type="password"
              placeholder="Re-enter new password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              disabled={isLoading}
              icon={Lock}
            />
            <p className="text-[11px] text-neutral-400">
              Must be at least 8 characters with at least one letter and one number.
            </p>
            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              className="w-full mt-2"
            >
              Set New Password
            </Button>
          </form>
        )}

        {/* Step 4: Success View */}
        {step === 'success' && (
          <div className="flex flex-col items-center gap-4 text-center py-2">
            <CheckCircle2 className="w-12 h-12 text-emerald-600" />
            <p className="text-sm font-medium text-neutral-800 dark:text-neutral-200">
              Password reset complete! You can now sign in with your new password.
            </p>
            <Button
              type="button"
              variant="primary"
              size="lg"
              onClick={onClose}
              className="w-full mt-2"
            >
              Return to Sign In
            </Button>
          </div>
        )}
      </div>
    </div>
  )
}
