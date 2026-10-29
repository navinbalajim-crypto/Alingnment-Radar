import React, { useState, useEffect, useRef } from 'react'
import { Button } from '../ui/Button'
import { Mail, ArrowLeft, RefreshCw } from 'lucide-react'

export function VerifyEmailCode({
  email,
  onVerify,
  onResend,
  onBack,
  initialCooldown = 60,
  isLoading = false,
  error = null,
}) {
  const [code, setCode] = useState(['', '', '', '', '', ''])
  const [cooldown, setCooldown] = useState(initialCooldown)
  const inputRefs = useRef([])

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = setInterval(() => {
      setCooldown((c) => Math.max(0, c - 1))
    }, 1000)
    return () => clearInterval(timer)
  }, [cooldown])

  useEffect(() => {
    // Focus first input box on mount
    if (inputRefs.current[0]) {
      inputRefs.current[0].focus()
    }
  }, [])

  const handleChange = (index, value) => {
    // Allow only digits
    const cleaned = value.replace(/\D/g, '')
    if (!cleaned) {
      const newCode = [...code]
      newCode[index] = ''
      setCode(newCode)
      return
    }

    // If user pastes multiple digits
    if (cleaned.length > 1) {
      const digits = cleaned.slice(0, 6).split('')
      const newCode = [...code]
      digits.forEach((d, i) => {
        if (index + i < 6) {
          newCode[index + i] = d
        }
      })
      setCode(newCode)
      const nextFocus = Math.min(5, index + digits.length)
      if (inputRefs.current[nextFocus]) {
        inputRefs.current[nextFocus].focus()
      }
      return
    }

    const newCode = [...code]
    newCode[index] = cleaned[0]
    setCode(newCode)

    // Move to next input
    if (index < 5 && cleaned[0]) {
      if (inputRefs.current[index + 1]) {
        inputRefs.current[index + 1].focus()
      }
    }
  }

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !code[index] && index > 0) {
      if (inputRefs.current[index - 1]) {
        inputRefs.current[index - 1].focus()
      }
    }
  }

  const handleSubmit = (e) => {
    e.preventDefault()
    const fullCode = code.join('')
    if (fullCode.length === 6) {
      onVerify(fullCode)
    }
  }

  const handleResendClick = async () => {
    if (cooldown > 0 || !onResend) return
    await onResend()
    setCooldown(60)
  }

  const isComplete = code.join('').length === 6

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <div className="text-center">
        <div className="mx-auto w-12 h-12 rounded-2xl bg-blue-50 dark:bg-blue-950/60 flex items-center justify-center text-apple-blue mb-3">
          <Mail className="w-6 h-6" />
        </div>
        <h3 className="text-lg font-semibold text-neutral-900 dark:text-neutral-100">
          Check your email
        </h3>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
          We sent a 6-digit verification code to <span className="font-medium text-neutral-700 dark:text-neutral-200">{email}</span>
        </p>
      </div>

      {error && (
        <div className="p-3 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl">
          {error}
        </div>
      )}

      {/* 6-box pin code input */}
      <div className="flex justify-center gap-2.5 my-2">
        {code.map((digit, index) => (
          <input
            key={index}
            ref={(el) => (inputRefs.current[index] = el)}
            type="text"
            inputMode="numeric"
            maxLength={1}
            value={digit}
            onChange={(e) => handleChange(index, e.target.value)}
            onKeyDown={(e) => handleKeyDown(index, e)}
            className="w-11 h-13 text-center text-xl font-bold font-mono bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 rounded-xl focus:outline-none focus:border-apple-blue focus:ring-3 focus:ring-apple-blue/20 text-neutral-900 dark:text-neutral-100 transition-all"
            disabled={isLoading}
          />
        ))}
      </div>

      <Button
        type="submit"
        variant="primary"
        size="lg"
        disabled={!isComplete}
        isLoading={isLoading}
        className="w-full"
      >
        Verify Code
      </Button>

      <div className="flex items-center justify-between text-xs text-neutral-500 pt-2 border-t border-neutral-100 dark:border-neutral-800">
        {onBack ? (
          <button
            type="button"
            onClick={onBack}
            className="flex items-center gap-1 hover:text-neutral-800 dark:hover:text-neutral-200 transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" /> Back
          </button>
        ) : <div />}

        <button
          type="button"
          onClick={handleResendClick}
          disabled={cooldown > 0}
          className="flex items-center gap-1 font-medium text-apple-blue disabled:text-neutral-400 disabled:cursor-not-allowed hover:underline"
        >
          <RefreshCw className="w-3 h-3" />
          {cooldown > 0 ? `Resend in ${cooldown}s` : 'Resend Code'}
        </button>
      </div>
    </form>
  )
}
