import { apiClient } from './apiClient'

export const gmailService = {
  async getConnectUrl(redirectUri) {
    const params = {}
    if (redirectUri) params.redirect_uri = redirectUri
    const res = await apiClient.get('/gmail/connect-url', { params })
    return res.data
  },

  async connectGmail(code, state, redirectUri) {
    const res = await apiClient.post('/gmail/callback', {
      code,
      state,
      redirect_uri: redirectUri || `${window.location.origin}/auth/google/callback`,
    })
    return res.data
  },

  async getStatus() {
    const res = await apiClient.get('/gmail/status')
    return res.data
  },

  async checkMessages() {
    const res = await apiClient.post('/gmail/check')
    return res.data
  },

  async getNotifications(limit = 50, offset = 0, unreadOnly = false) {
    const params = { limit, offset, unread_only: unreadOnly }
    const res = await apiClient.get('/gmail/notifications', { params })
    return res.data
  },

  async markAsRead(notificationId) {
    const res = await apiClient.post(`/gmail/notifications/${notificationId}/read`)
    return res.data
  },

  async markAllAsRead() {
    const res = await apiClient.post('/gmail/notifications/read-all')
    return res.data
  },

  async disconnect() {
    const res = await apiClient.delete('/gmail')
    return res.data
  },
}
