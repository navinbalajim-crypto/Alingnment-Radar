import { apiClient, setTokens, clearTokens, getRefreshToken } from './apiClient'

export const authService = {
  // Registration flow
  async requestRegisterCode(email) {
    const res = await apiClient.post('/auth/register/request-code', { email })
    return res.data
  },

  async verifyRegisterCode(email, code) {
    const res = await apiClient.post('/auth/register/verify-code', { email, code })
    return res.data
  },

  async checkUsernameAvailability(username) {
    const res = await apiClient.get('/users/username-availability', {
      params: { username },
    })
    return res.data
  },

  async completeRegistration(registrationTicket, username, displayName, password) {
    const payload = {
      registration_ticket: registrationTicket,
      username,
      display_name: displayName || null,
    }
    if (password) payload.password = password

    const res = await apiClient.post('/auth/register/complete', payload)
    const data = res.data
    setTokens(data.access_token, data.refresh_token)
    localStorage.setItem('ar_user', JSON.stringify(data.user))
    return data
  },

  // Password Login
  async loginWithPassword(username, password) {
    const res = await apiClient.post('/auth/login/password', {
      username,
      password,
    })
    const data = res.data
    setTokens(data.access_token, data.refresh_token)
    localStorage.setItem('ar_user', JSON.stringify(data.user))
    return data
  },

  // Password Recovery
  async forgotPassword(email) {
    const res = await apiClient.post('/auth/password/forgot', { email })
    return res.data
  },

  async verifyResetCode(email, code) {
    const res = await apiClient.post('/auth/password/verify-code', { email, code })
    return res.data
  },

  async resetPassword(resetTicket, newPassword) {
    const res = await apiClient.post('/auth/password/reset', {
      reset_ticket: resetTicket,
      new_password: newPassword,
    })
    return res.data
  },

  async setPassword(newPassword) {
    const res = await apiClient.post('/auth/password/set', {
      new_password: newPassword,
    })
    return res.data
  },

  // Email Code Login flow (preserved for existing users)
  async requestLoginCode(email) {
    const res = await apiClient.post('/auth/login/request-code', { email })
    return res.data
  },

  async verifyLoginCode(email, code) {
    const res = await apiClient.post('/auth/login/verify-code', { email, code })
    const data = res.data
    setTokens(data.access_token, data.refresh_token)
    localStorage.setItem('ar_user', JSON.stringify(data.user))
    return data
  },

  // Google OAuth flow
  async getGoogleAuthUrl(redirectUri) {
    const params = {}
    if (redirectUri) params.redirect_uri = redirectUri
    const res = await apiClient.get('/auth/google/url', { params })
    return res.data
  },

  async loginWithGoogle(code, state, redirectUri) {
    const res = await apiClient.post('/auth/google/callback', {
      code,
      state: state || null,
      redirect_uri: redirectUri || `${window.location.origin}/auth/google/callback`,
    })
    const data = res.data
    setTokens(data.access_token, data.refresh_token)
    localStorage.setItem('ar_user', JSON.stringify(data.user))
    return data
  },

  // Session & User
  async getCurrentUser() {
    const res = await apiClient.get('/users/me')
    localStorage.setItem('ar_user', JSON.stringify(res.data))
    return res.data
  },

  async uploadAvatar(file) {
    const formData = new FormData()
    formData.append('file', file)
    // `apiClient` sets a default 'application/json' Content-Type on every request. Simply
    // omitting a header here does NOT clear that default -- axios still sees
    // Content-Type: application/json and JSON-stringifies the FormData instead of sending
    // it as a file, so every upload silently fails. Explicitly clearing it with `undefined`
    // is required so the browser can set its own multipart boundary.
    const res = await apiClient.post('/users/me/avatar', formData, {
      headers: { 'Content-Type': undefined },
    })
    localStorage.setItem('ar_user', JSON.stringify(res.data))
    return res.data
  },

  async searchUsers(username) {
    const res = await apiClient.get('/users/search', {
      params: { username },
    })
    return res.data
  },

  async logout() {
    const token = getRefreshToken()
    try {
      if (token) {
        await apiClient.post('/auth/logout', { refresh_token: token })
      }
    } catch (err) {
      console.warn('Logout API call failed or token already invalid:', err)
    } finally {
      clearTokens()
    }
  },
}
