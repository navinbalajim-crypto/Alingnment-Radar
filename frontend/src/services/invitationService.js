import { apiClient, setTokens } from './apiClient'

export const invitationService = {
  async previewInvitation(token) {
    const res = await apiClient.get(`/invitations/${encodeURIComponent(token)}`)
    return res.data
  },

  async requestCode(token, email) {
    const res = await apiClient.post(`/invitations/${encodeURIComponent(token)}/request-code`, {
      email,
    })
    return res.data
  },

  async verifyCode(token, email, code) {
    const res = await apiClient.post(`/invitations/${encodeURIComponent(token)}/verify-code`, {
      email,
      code,
    })
    const data = res.data
    if (data.tokens && data.tokens.access_token) {
      setTokens(data.tokens.access_token, data.tokens.refresh_token)
      if (data.tokens.user) {
        localStorage.setItem('ar_user', JSON.stringify(data.tokens.user))
      }
    }
    return data
  },

  async completeRegistration(token, registrationTicket, username, displayName) {
    const res = await apiClient.post(`/invitations/${encodeURIComponent(token)}/complete-registration`, {
      registration_ticket: registrationTicket,
      username,
      display_name: displayName || null,
    })
    const data = res.data
    setTokens(data.access_token, data.refresh_token)
    if (data.user) {
      localStorage.setItem('ar_user', JSON.stringify(data.user))
    }
    return data
  },
}
