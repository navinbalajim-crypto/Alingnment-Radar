import React, { useState } from 'react'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { authService } from '../../services/authService'
import { Lock, ShieldCheck, X } from 'lucide-react'

export function SetPasswordModal({ isOpen, onClose, onPasswordSet }) {
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const [success, setSuccess] = useState(false)

  if (!isOpen) return null

  const handleSetPassword = async (e) => {
    e.preventDefault()
    if (password.length < 8) {
      setError('Password must be at least 8 characters long.')
      return
    }
    if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
      setError('Password must contain at least one letter and one number.')
      return
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      await authService.setPassword(password)
      setSuccess(true)
      if (onPasswordSet) onPasswordSet()
      setTimeout(() => {
        onClose()
      }, 1500)
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to set password.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="relative w-full max-w-md bg-white dark:bg-neutral-900 rounded-3xl shadow-apple border border-black/[0.08] dark:border-white/[0.1] p-7 transition-all">
        <button
          onClick={onClose}
          className="absolute top-5 right-5 p-1.5 rounded-full text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
        >
          <X className="w-5 h-5" />
        </button>

        <div className="text-center mb-6">
          <div className="mx-auto w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-950/60 flex items-center justify-center text-emerald-600 mb-3">
            <Lock className="w-6 h-6" />
          </div>
          <h2 className="text-lg font-bold text-neutral-900 dark:text-white">
            Set Your Password
          </h2>
          <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
            Establish a password to sign in with your username anytime, while keeping Google Sign-In available.
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl">
            {error}
          </div>
        )}

        {success ? (
          <div className="text-center py-4">
            <ShieldCheck className="w-12 h-12 text-emerald-600 mx-auto mb-2" />
            <p className="text-sm font-semibold text-neutral-900 dark:text-white">
              Password set successfully!
            </p>
          </div>
        ) : (
          <form onSubmit={handleSetPassword} className="flex flex-col gap-4">
            <Input
              label="New Password"
              type="password"
              placeholder="At least 8 characters"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              disabled={isLoading}
              icon={Lock}
              autoFocus
            />
            <Input
              label="Confirm Password"
              type="password"
              placeholder="Confirm new password"
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
              Save Password
            </Button>
          </form>
        )}
      </div>
    </div>
  )
}
