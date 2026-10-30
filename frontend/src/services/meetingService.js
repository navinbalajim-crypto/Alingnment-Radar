import { apiClient } from './apiClient'

export const meetingService = {
  /**
   * Request Google Meet meeting creation for a conversation.
   * If Google Meet scope is missing or unauthenticated, response contains `requires_auth: true` and `authorization_url`.
   */
  async createMeeting(conversationId, clientToken = null, redirectUri = null, fallbackInstant = true) {
    const res = await apiClient.post(`/conversations/${conversationId}/meet`, {
      client_token: clientToken,
      redirect_uri: redirectUri || `${window.location.origin}/auth/google/callback`,
      fallback_instant: Boolean(fallbackInstant),
    })
    return res.data
  },

  /**
   * Get Google OAuth consent URL configured specifically for Google Meet spaces.
   */
  async getAuthUrl(conversationId, redirectUri = null) {
    const params = {}
    if (redirectUri) params.redirect_uri = redirectUri
    const res = await apiClient.get(`/conversations/${conversationId}/meet/auth-url`, { params })
    return res.data
  },

  /**
   * Exchange OAuth callback authorization code for Google Meet access token.
   */
  async connectGoogleMeet(code, state, redirectUri = null) {
    const res = await apiClient.post('/auth/google/meet/callback', {
      code,
      state,
      redirect_uri: redirectUri || `${window.location.origin}/auth/google/callback`,
    })
    return res.data
  },
}
