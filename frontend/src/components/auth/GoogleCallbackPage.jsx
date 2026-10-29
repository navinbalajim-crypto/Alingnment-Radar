import React, { useEffect, useState, useRef } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { authService } from '../../services/authService'
import { contactService } from '../../services/contactService'
import { gmailService } from '../../services/gmailService'
import { meetingService } from '../../services/meetingService'
import { useAuth } from '../../context/AuthContext'
import { Compass, AlertCircle, ArrowLeft, Loader2 } from 'lucide-react'
import { Button } from '../ui/Button'

export function GoogleCallbackPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { handleAuthSuccess } = useAuth()

  const [status, setStatus] = useState('processing') // 'processing' | 'error' | 'success'
  const [statusTitle, setStatusTitle] = useState('Authenticating with Google')
  const [statusSubtitle, setStatusSubtitle] = useState('Verifying your credentials and preparing your secure real-time alignment workspace...')
  const [errorMessage, setErrorMessage] = useState(null)
  const [detectedPurpose, setDetectedPurpose] = useState('login')
  const isExecutingRef = useRef(false)

  useEffect(() => {
    if (isExecutingRef.current) return
    isExecutingRef.current = true

    const code = searchParams.get('code')
    const error = searchParams.get('error')
    const state = searchParams.get('state')

    // Parse state purpose client-side for immediate UX feedback
    let purpose = 'login'
    if (state) {
      try {
        const parts = state.split('.')
        if (parts.length >= 2) {
          const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
          const payload = JSON.parse(atob(base64))
          if (payload?.purpose) {
            purpose = payload.purpose
          }
        }
      } catch (e) {
        console.warn('Could not parse OAuth state JWT:', e)
      }
    }
    setDetectedPurpose(purpose)

    if (error) {
      setStatus('error')
      if (purpose === 'contacts') {
        setErrorMessage(
          error === 'access_denied'
            ? 'Google Contacts access was not granted. Your existing account and direct messaging remain fully functional, and you can still search teammates by username.'
            : `Google Contacts authorization failed: ${error}`
        )
      } else if (purpose === 'gmail') {
        setErrorMessage(
          error === 'access_denied'
            ? 'Gmail notification access was not granted. Alignment Radar will continue running normally without Gmail alerts.'
            : `Gmail authorization failed: ${error}`
        )
      } else if (purpose === 'connect_meet' || purpose === 'meet') {
        setErrorMessage(
          error === 'access_denied'
            ? 'Google blocked access because this app is currently in Testing mode. To enable it: add your Google account as a Test User in Google Cloud Console -> OAuth consent screen -> Test users, or use the Instant Meeting option in the chat header.'
            : `Google Meet authorization failed: ${error}`
        )
      } else {
        setErrorMessage(
          error === 'access_denied'
            ? 'Google sign-in was cancelled or permissions were denied.'
            : `Google authorization failed: ${error}`
        )
      }
      return
    }

    if (!code) {
      setStatus('error')
      setErrorMessage('No authorization code was received from Google.')
      return
    }

    const processOAuth = async () => {
      try {
        if (purpose === 'contacts') {
          setStatusTitle('Linking Google Contacts')
          setStatusSubtitle('Securing connection and synchronizing registered teammates from your address book...')
          await contactService.connectGoogleContacts(code, state)
          setStatus('success')
          setTimeout(() => {
            navigate('/chat', { replace: true, state: { toast: 'Google Contacts connected successfully!' } })
          }, 1200)
        } else if (purpose === 'gmail') {
          setStatusTitle('Linking Gmail Notifications')
          setStatusSubtitle('Configuring secure, read-only metadata alerts for incoming emails...')
          await gmailService.connectGmail(code, state)
          setStatus('success')
          setTimeout(() => {
            navigate('/chat', { replace: true, state: { toast: 'Gmail notifications connected successfully!' } })
          }, 1200)
        } else if (purpose === 'connect_meet' || purpose === 'meet') {
          setStatusTitle('Connecting Google Meet')
          setStatusSubtitle('Authorizing real-time meeting space creation for your team...')
          await meetingService.connectGoogleMeet(code, state)
          setStatus('success')
          setTimeout(() => {
            navigate('/chat', { replace: true, state: { toast: 'Google Meet connected successfully! You can now create call links.' } })
          }, 1200)
        } else {
          // Default login flow
          setStatusTitle('Authenticating with Google')
          setStatusSubtitle('Verifying your credentials and preparing your secure real-time alignment workspace...')
          const data = await authService.loginWithGoogle(code, state)
          handleAuthSuccess(data.user, data.access_token)
          navigate('/chat', { replace: true })
        }
      } catch (err) {
        console.error('OAuth callback execution error:', err)
        setStatus('error')
        const detail =
          err.response?.data?.message ||
          err.response?.data?.detail ||
          'Failed to complete Google authorization. Please try again.'
        setErrorMessage(detail)
      }
    }

    processOAuth()
  }, [searchParams, handleAuthSuccess, navigate])

  const isIntegration =
    detectedPurpose === 'contacts' ||
    detectedPurpose === 'gmail' ||
    detectedPurpose === 'connect_meet' ||
    detectedPurpose === 'meet'

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-[#F2F2F7] dark:bg-neutral-950">
      <div className="w-full max-w-md bg-white dark:bg-neutral-900 rounded-3xl shadow-apple border border-black/[0.06] dark:border-white/[0.08] p-8 text-center transition-all">
        {/* Brand Header */}
        <div className="flex items-center justify-center gap-2.5 mb-8">
          <div className="w-10 h-10 rounded-2xl bg-neutral-900 dark:bg-white flex items-center justify-center text-white dark:text-neutral-900 shadow-subtle">
            <Compass className="w-5 h-5" />
          </div>
          <div className="text-left">
            <h1 className="text-xl font-bold tracking-tight text-neutral-900 dark:text-white">
              Alignment Radar
            </h1>
            <p className="text-[11px] text-neutral-500 font-medium tracking-wide uppercase">
              AI Real-Time Messaging
            </p>
          </div>
        </div>

        {status === 'processing' && (
          <div className="flex flex-col items-center justify-center py-6 gap-4">
            <Loader2 className="w-10 h-10 text-apple-blue animate-spin" />
            <div>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-white">
                {statusTitle}
              </h2>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 max-w-xs mx-auto">
                {statusSubtitle}
              </p>
            </div>
          </div>
        )}

        {status === 'success' && (
          <div className="flex flex-col items-center justify-center py-6 gap-4">
            <div className="w-12 h-12 rounded-2xl bg-green-50 dark:bg-green-950/50 flex items-center justify-center text-green-600 border border-green-200 dark:border-green-900/50">
              <Compass className="w-6 h-6 animate-pulse" />
            </div>
            <div>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-white">
                Connected Successfully
              </h2>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1">
                Redirecting back to your workspace...
              </p>
            </div>
          </div>
        )}

        {status === 'error' && (
          <div className="flex flex-col items-center justify-center py-4 gap-5">
            <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-950/50 flex items-center justify-center text-red-500 border border-red-200 dark:border-red-900/50">
              <AlertCircle className="w-6 h-6" />
            </div>

            <div className="space-y-1.5">
              <h2 className="text-base font-semibold text-neutral-900 dark:text-white">
                {isIntegration ? 'Integration Cancelled or Failed' : 'Authentication Failed'}
              </h2>
              <p className="text-xs text-red-600 dark:text-red-400 max-w-xs mx-auto leading-relaxed">
                {errorMessage}
              </p>
            </div>

            <div className="w-full pt-4 border-t border-neutral-100 dark:border-neutral-800 flex flex-col gap-2">
              <Button
                variant="primary"
                size="md"
                className="w-full"
                onClick={() => navigate(isIntegration ? '/chat' : '/login', { replace: true })}
              >
                <ArrowLeft className="w-4 h-4 mr-1.5" />
                {isIntegration ? 'Return to Chat' : 'Return to Sign In'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

