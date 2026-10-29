import { apiClient } from './apiClient'

const DRAFT_REQUEST_TIMEOUT_MS = 15000
const SUGGEST_REQUEST_TIMEOUT_MS = 5000

export const aiService = {
  async analyzeDraft(conversationId, draft, draftRevision, signal) {
    try {
      const res = await apiClient.post('/draft/analyze', {
        conversation_id: conversationId,
        draft,
        draft_revision: draftRevision,
      }, { signal, timeout: DRAFT_REQUEST_TIMEOUT_MS })
      return res.data
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        return null
      }
      throw err
    }
  },

  // Opt-in AI autocomplete. The server checks the user's stored consent; nothing sent here can grant it.
  async suggestDraft(conversationId, draft, draftRevision, signal) {
    try {
      const res = await apiClient.post('/draft/suggest', {
        conversation_id: conversationId,
        draft,
        draft_revision: draftRevision,
      }, { signal, timeout: SUGGEST_REQUEST_TIMEOUT_MS })
      return res.data
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        return null
      }
      throw err
    }
  },

  async getAiPreferences() {
    const res = await apiClient.get('/users/me/ai-preferences')
    return res.data
  },

  async updateAiPreferences(changes) {
    const res = await apiClient.put('/users/me/ai-preferences', changes)
    return res.data
  },

  async getDraftRecommendations(conversationId, draft, draftRevision, signal) {
    try {
      const res = await apiClient.post('/draft/recommendations', {
        conversation_id: conversationId,
        draft,
        draft_revision: draftRevision,
      }, { signal, timeout: DRAFT_REQUEST_TIMEOUT_MS })
      return res.data
    } catch (err) {
      if (err.name === 'CanceledError' || err.code === 'ERR_CANCELED') {
        return null
      }
      throw err
    }
  },

  async getAiItems(conversationId) {
    const res = await apiClient.get(`/conversations/${conversationId}/ai-items`)
    return res.data
  },

  async shareRecommendation(conversationId, recommendationId) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/recommendations/${recommendationId}/share`
    )
    return res.data
  },

  async requestRecommendations(conversationId, { query, category } = {}) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/recommendations/request`,
      { query, category }
    )
    return res.data
  },

  async triggerAlignment(conversationId) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/alignment/analyze`,
      {}
    )
    return res.data
  },

  async confirmAlignment(conversationId, findingId, { comment } = {}) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/alignment/${findingId}/confirm`,
      { comment }
    )
    return res.data
  },

  async requestClarification(conversationId, findingId) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/alignment/${findingId}/request-clarification`,
      {}
    )
    return res.data
  },

  async resolveAlignment(conversationId, findingId, { evidence } = {}) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/alignment/${findingId}/resolve`,
      { evidence }
    )
    return res.data
  },

  async dismissAlignment(conversationId, findingId, { reason } = {}) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/alignment/${findingId}/dismiss`,
      { reason }
    )
    return res.data
  },

  async dismissRecommendation(conversationId, recommendationId, { reason } = {}) {
    const res = await apiClient.post(
      `/conversations/${conversationId}/recommendations/${recommendationId}/dismiss`,
      { reason }
    )
    return res.data
  },
}
