import React, { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { authService } from '../services/authService'
import { registerLogoutHandler, getAccessToken, clearTokens, setTokens } from '../services/apiClient'
import { socketService } from '../services/socketService'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const stored = localStorage.getItem('ar_user')
      return stored ? JSON.parse(stored) : null
    } catch {
      return null
    }
  })
  const [isAuthenticated, setIsAuthenticated] = useState(() => !!getAccessToken())
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(async () => {
    try {
      await authService.logout()
    } finally {
      setUser(null)
      setIsAuthenticated(false)
      socketService.disconnect()
    }
  }, [])

  // Register apiClient 401 callback
  useEffect(() => {
    registerLogoutHandler(() => {
      setUser(null)
      setIsAuthenticated(false)
      socketService.disconnect()
    })
  }, [])

  // Verify current user profile on initial mount if token exists
  useEffect(() => {
    const verifyUser = async () => {
      try {
        const urlParams = new URLSearchParams(window.location.search)
        const queryToken = urlParams.get('access_token') || urlParams.get('token')
        if (queryToken) {
          setTokens(queryToken, null)
          window.history.replaceState({}, document.title, window.location.pathname)
        }
      } catch {
        // ignore url parsing error
      }

      const token = getAccessToken()
      if (!token) {
        setIsLoading(false)
        return
      }

      try {
        const currentUser = await authService.getCurrentUser()
        setUser(currentUser)
        setIsAuthenticated(true)
        socketService.connect(token)
      } catch (err) {
        console.warn('Initial session validation failed:', err)
        clearTokens()
        setUser(null)
        setIsAuthenticated(false)
      } finally {
        setIsLoading(false)
      }
    }

    verifyUser()
  }, [])

  const handleAuthSuccess = (userData, accessToken) => {
    setUser(userData)
    setIsAuthenticated(true)
    socketService.connect(accessToken)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        setUser,
        isAuthenticated,
        isLoading,
        handleAuthSuccess,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
