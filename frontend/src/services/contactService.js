import { apiClient } from './apiClient'

export const contactService = {
  async getContacts(query, limit = 100, offset = 0) {
    const params = { limit, offset }
    if (query) params.query = query
    const res = await apiClient.get('/contacts', { params })
    return res.data
  },

  async getGoogleContactsConnectUrl(redirectUri) {
    const params = {}
    if (redirectUri) params.redirect_uri = redirectUri
    const res = await apiClient.get('/contacts/google/connect-url', { params })
    return res.data
  },

  async connectGoogleContacts(code, state, redirectUri) {
    const res = await apiClient.post('/contacts/google/callback', {
      code,
      state,
      redirect_uri: redirectUri || `${window.location.origin}/auth/google/callback`,
    })
    return res.data
  },

  async getGoogleStatus() {
    const res = await apiClient.get('/contacts/google/status')
    return res.data
  },

  async syncGoogleContacts() {
    const res = await apiClient.post('/contacts/sync-google')
    return res.data
  },

  async disconnectGoogle() {
    const res = await apiClient.delete('/contacts/google')
    return res.data
  },
}

