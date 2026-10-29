import React, { useState, useEffect } from 'react'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { authService } from '../../services/authService'
import { Check, X, User, Sparkles } from 'lucide-react'

export function ChooseUsername({
  email,
  onComplete,
  isLoading = false,
  error = null,
}) {
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [validationError, setValidationError] = useState('')
  const [isChecking, setIsChecking] = useState(false)
  const [isAvailable, setIsAvailable] = useState(null)
  const [checkMessage, setCheckMessage] = useState('')

  // Debounced username availability check
  useEffect(() => {
    const trimmed = username.trim()
    if (trimmed.length < 3) {
      setIsAvailable(null)
      setCheckMessage('')
      return
    }

    const timer = setTimeout(async () => {
      setIsChecking(true)
      try {
        const res = await authService.checkUsernameAvailability(trimmed)
        setIsAvailable(res.available)
        setCheckMessage(res.message)
      } catch (err) {
        setIsAvailable(false)
        setCheckMessage('Could not verify username availability')
      } finally {
        setIsChecking(false)
      }
    }, 400)

    return () => clearTimeout(timer)
  }, [username])

  const handleSubmit = (e) => {
    e.preventDefault()
    setValidationError('')

    if (password) {
      if (password.length < 8) {
        setValidationError('Password must be at least 8 characters long.')
        return
      }
      if (!/[A-Za-z]/.test(password) || !/[0-9]/.test(password)) {
        setValidationError('Password must contain at least one letter and one number.')
        return
      }
      if (password !== confirmPassword) {
        setValidationError('Passwords do not match.')
        return
      }
    }

    if (isAvailable && username.trim().length >= 3) {
      const payload = {
        username: username.trim(),
        displayName: displayName.trim() || undefined,
      }
      if (password) {
        payload.password = password
      }
      onComplete(payload)
    }
  }

  const effectiveError = validationError || error

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="text-center">
        <div className="mx-auto w-12 h-12 rounded-2xl bg-emerald-50 dark:bg-emerald-950/60 flex items-center justify-center text-emerald-600 mb-3">
          <Sparkles className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Finish Account Setup
        </h3>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
          Select a unique username and password to access Alignment Radar.
        </p>
      </div>

      {effectiveError && (
        <div className="p-3 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl">
          {effectiveError}
        </div>
      )}

      <div>
        <div className="relative">
          <Input
            label="Username (unique identifier)"
            placeholder="e.g. alex_chen"
            value={username}
            onChange={(e) => setUsername(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ''))}
            disabled={isLoading}
            required
            minLength={3}
            maxLength={30}
            icon={User}
          />
          <div className="absolute right-3 top-[34px] flex items-center">
            {isChecking && (
              <span className="text-xs text-neutral-400 animate-pulse">Checking...</span>
            )}
            {!isChecking && isAvailable === true && (
              <span className="flex items-center text-xs text-emerald-600 font-medium">
                <Check className="w-4 h-4 mr-1" /> Available
              </span>
            )}
            {!isChecking && isAvailable === false && (
              <span className="flex items-center text-xs text-red-500 font-medium">
                <X className="w-4 h-4 mr-1" /> Unavailable
              </span>
            )}
          </div>
        </div>
        {checkMessage && (
          <p
            className={`text-xs mt-1 ${
              isAvailable ? 'text-emerald-600' : 'text-red-500'
            }`}
          >
            {checkMessage}
          </p>
        )}
      </div>

      <Input
        label="Display Name (optional)"
        placeholder="e.g. Alex Chen"
        value={displayName}
        onChange={(e) => setDisplayName(e.target.value)}
        disabled={isLoading}
        maxLength={100}
        helperText="Your real name shown in chats alongside your handle."
      />

      <Input
        label="Password"
        type="password"
        placeholder="Min 8 characters with letter & number"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        disabled={isLoading}
      />

      <Input
        label="Confirm Password"
        type="password"
        placeholder="Re-enter your password"
        value={confirmPassword}
        onChange={(e) => setConfirmPassword(e.target.value)}
        disabled={isLoading}
      />

      <Button
        type="submit"
        variant="primary"
        size="lg"
        disabled={!isAvailable || username.trim().length < 3 || isChecking}
        isLoading={isLoading}
        className="w-full mt-2"
      >
        Complete Registration
      </Button>
    </form>
  )
}
