import React from 'react'
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { AppShell } from '../components/layout/AppShell'
import { LoginPage } from '../components/auth/LoginPage'
import { RegisterPage } from '../components/auth/RegisterPage'
import { GoogleCallbackPage } from '../components/auth/GoogleCallbackPage'
import { JoinGroupPage } from '../components/groups/JoinGroupPage'
import { LandingPage } from '../components/landing/LandingPage'
import { PrivacyPolicyPage } from '../components/legal/PrivacyPolicyPage'
import { TermsOfServicePage } from '../components/legal/TermsOfServicePage'
import { useAuth } from '../context/AuthContext'

function ProtectedRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F2F2F7] dark:bg-neutral-950">
        <div className="w-8 h-8 rounded-full border-2 border-apple-blue border-t-transparent animate-spin" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return children
}

function PublicAuthRoute({ children }) {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#F2F2F7] dark:bg-neutral-950">
        <div className="w-8 h-8 rounded-full border-2 border-apple-blue border-t-transparent animate-spin" />
      </div>
    )
  }

  if (isAuthenticated) {
    return <Navigate to="/chat" replace />
  }

  return children
}

export const router = createBrowserRouter([
  {
    // Landing page for visitors; signed-in users still go straight to /chat.
    path: '/',
    element: (
      <PublicAuthRoute>
        <LandingPage />
      </PublicAuthRoute>
    ),
  },
  {
    path: '/login',
    element: (
      <PublicAuthRoute>
        <LoginPage />
      </PublicAuthRoute>
    ),
  },
  {
    path: '/register',
    element: (
      <PublicAuthRoute>
        <RegisterPage />
      </PublicAuthRoute>
    ),
  },
  {
    path: '/auth/google/callback',
    element: <GoogleCallbackPage />,
  },
  {
    path: '/chat',
    element: (
      <ProtectedRoute>
        <AppShell />
      </ProtectedRoute>
    ),
  },
  {
    path: '/invitations/:token',
    element: <JoinGroupPage />,
  },
  {
    path: '/privacy',
    element: <PrivacyPolicyPage />,
  },
  {
    path: '/terms',
    element: <TermsOfServicePage />,
  },
  {
    path: '*',
    element: <Navigate to="/chat" replace />,
  },
])
