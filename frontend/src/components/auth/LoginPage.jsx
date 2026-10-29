import { useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { GoogleButton } from '../ui/GoogleButton'
import { VerifyEmailCode } from './VerifyEmailCode'
import { ForgotPasswordModal } from './ForgotPasswordModal'
import { SetPasswordModal } from './SetPasswordModal'
import { AuthLayout, OrDivider } from './AuthLayout'
import { authService } from '../../services/authService'
import { useAuth } from '../../context/AuthContext'
import { Mail, Lock, User, ShieldCheck, UserPlus, KeyRound } from 'lucide-react'

export function LoginPage() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const { handleAuthSuccess } = useAuth()

  // Sign-in modes: 'password' (standard) | 'email_code' (passwordless) | 'verify_code'
  const [authMode, setAuthMode] = useState('password')
  const [username, setUsername] = useState(searchParams.get('username') || '')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState(searchParams.get('email') || '')
  const [cooldownSeconds, setCooldownSeconds] = useState(60)

  // Modals
  const [isForgotOpen, setIsForgotOpen] = useState(false)
  const [isSetPasswordOpen, setIsSetPasswordOpen] = useState(false)

  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  // 1. Username + Password Login
  const handlePasswordLogin = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password) return

    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.loginWithPassword(username.trim(), password)
      handleAuthSuccess(res.user, res.access_token)
      navigate('/chat', { replace: true })
    } catch (err) {
      const msg =
        err.response?.data?.message ||
        err.response?.data?.detail ||
        'Invalid username or password. Please try again.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  // 2. Email verification code request (preserved for existing users)
  const handleRequestCode = async (e) => {
    e.preventDefault()
    if (!email.trim()) return

    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.requestLoginCode(email.trim().toLowerCase())
      setCooldownSeconds(res.cooldown_seconds || 60)
      setAuthMode('verify_code')
    } catch (err) {
      const msg =
        err.response?.data?.message ||
        err.response?.data?.detail ||
        'Failed to send login code. Please check your email.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  const handleResendCode = async () => {
    setError(null)
    try {
      const res = await authService.requestLoginCode(email.trim().toLowerCase())
      setCooldownSeconds(res.cooldown_seconds || 60)
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || 'Failed to resend code.'
      setError(msg)
    }
  }

  const handleVerifyCode = async (code) => {
    setIsLoading(true)
    setError(null)
    try {
      const res = await authService.verifyLoginCode(email.trim().toLowerCase(), code)
      handleAuthSuccess(res.user, res.access_token)

      // If user does not have a password yet, offer password setup
      if (res.user && !res.user.has_password && !res.has_password) {
        setIsSetPasswordOpen(true)
      } else {
        navigate('/chat', { replace: true })
      }
    } catch (err) {
      const msg = err.response?.data?.message || err.response?.data?.detail || 'Invalid or expired login code.'
      setError(msg)
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <AuthLayout
      overlays={
        <>
          {/* Forgot Password Modal */}
          <ForgotPasswordModal
            isOpen={isForgotOpen}
            onClose={() => setIsForgotOpen(false)}
            initialEmail={email || ''}
          />

          {/* Existing User Password Migration Modal */}
          <SetPasswordModal
            isOpen={isSetPasswordOpen}
            onClose={() => {
              setIsSetPasswordOpen(false)
              navigate('/chat', { replace: true })
            }}
            onPasswordSet={() => {
              navigate('/chat', { replace: true })
            }}
          />
        </>
      }
    >
        {/* Header Title */}
        <div className="mb-6">
          <h1 className="text-2xl font-bold tracking-tight text-neutral-900 dark:text-neutral-50">
            Welcome back
          </h1>
          <p className="text-sm text-neutral-500 dark:text-neutral-400 mt-1.5">
            {authMode === 'password'
              ? 'Sign in to continue your conversations and stay aligned.'
              : 'Enter your registered email to receive a sign-in code.'}
          </p>
        </div>

        {error && (
          <div className="mb-5 p-3.5 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl flex flex-col gap-2">
            <div>{error}</div>
            {error.toLowerCase().includes('register') && (
              <button
                type="button"
                onClick={() => navigate(`/register?email=${encodeURIComponent(email || username)}`)}
                className="self-start text-xs font-semibold text-apple-blue dark:text-blue-400 hover:underline flex items-center gap-1.5 pt-1 border-t border-red-200/60 dark:border-red-800/60 w-full"
              >
                <UserPlus className="w-3.5 h-3.5" />
                New here? Create an account →
              </button>
            )}
          </div>
        )}

        {/* PRIMARY FORM: Username + Password */}
        {authMode === 'password' && (
          <form onSubmit={handlePasswordLogin} className="flex flex-col gap-4">
            <Input
              label="Username"
              type="text"
              placeholder="Enter your username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              disabled={isLoading}
              icon={User}
              autoFocus
            />

            <div>
              <Input
                label="Password"
                type="password"
                placeholder="Enter your password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={isLoading}
                icon={Lock}
              />
              <div className="flex justify-end mt-1.5">
                <button
                  type="button"
                  onClick={() => setIsForgotOpen(true)}
                  className="text-xs font-medium text-apple-blue dark:text-blue-400 hover:underline transition-colors"
                >
                  Forgot password?
                </button>
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={isLoading}
              className="w-full mt-1"
            >
              Sign In
            </Button>

            <p className="text-center text-xs text-neutral-500 dark:text-neutral-400">
              New to Alignment Radar?{' '}
              <Link to="/register" className="font-semibold text-apple-blue dark:text-blue-400 hover:underline">
                Create an account
              </Link>
            </p>

            <OrDivider />

            {/* Existing Google Sign-In */}
            <GoogleButton label="Continue with Google" onError={(err) => setError(err)} />

            {/* Existing Email Code Fallback */}
            <button
              type="button"
              onClick={() => { setAuthMode('email_code'); setError(null) }}
              className="w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-xl text-xs font-semibold text-neutral-800 dark:text-neutral-100 bg-white dark:bg-neutral-800/80 hover:bg-neutral-50 dark:hover:bg-neutral-700/80 border border-black/[0.08] dark:border-white/[0.12] shadow-subtle transition-all active:scale-[0.985] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue"
            >
              <Mail className="w-4 h-4 text-neutral-500" />
              Continue with Email
            </button>
          </form>
        )}

        {/* ALTERNATIVE FORM: Email Code Request */}
        {authMode === 'email_code' && (
          <form onSubmit={handleRequestCode} className="flex flex-col gap-4">
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
              className="w-full mt-1"
            >
              Send Sign-in Code
            </Button>

            <p className="text-center text-xs text-neutral-500 dark:text-neutral-400">
              New to Alignment Radar?{' '}
              <Link to="/register" className="font-semibold text-apple-blue dark:text-blue-400 hover:underline">
                Create an account
              </Link>
            </p>

            <button
              type="button"
              onClick={() => { setAuthMode('password'); setError(null) }}
              className="text-xs text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-200 text-center transition-colors pt-1"
            >
              ← Back to Username & Password sign in
            </button>

            <OrDivider />

            <GoogleButton label="Continue with Google" onError={(err) => setError(err)} />
          </form>
        )}

        {/* VERIFICATION FORM */}
        {authMode === 'verify_code' && (
          <VerifyEmailCode
            email={email}
            initialCooldown={cooldownSeconds}
            onVerify={handleVerifyCode}
            onResend={handleResendCode}
            onBack={() => setAuthMode('email_code')}
            isLoading={isLoading}
            error={error}
          />
        )}
    </AuthLayout>
  )
}
