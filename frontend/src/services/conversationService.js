import { apiClient } from './apiClient'

export const conversationService = {
  async listConversations() {
    const res = await apiClient.get('/conversations')
    return res.data
  },

  async getDirectConversation(username) {
    const res = await apiClient.post(`/conversations/direct/${encodeURIComponent(username)}`)
    return res.data
  },

  async getMessages(conversationId, { limit = 50, before = null } = {}) {
    const params = { limit }
    if (before) {
      params.before = before
    }
    const res = await apiClient.get(`/conversations/${conversationId}/messages`, { params })
    return res.data
  },

  async deleteMessage(conversationId, messageId, deleteType = 'me') {
    const res = await apiClient.delete(`/conversations/${conversationId}/messages/${messageId}`, {
      params: { delete_type: deleteType },
    })
    return res.data
  },

  async uploadAttachment(conversationId, file, caption = null, clientId = null, replyToMessageId = null) {
    const formData = new FormData()
    formData.append('file', file)
    if (caption) formData.append('caption', caption)
    if (clientId) formData.append('client_id', clientId)
    if (replyToMessageId) formData.append('reply_to_message_id', replyToMessageId)

    // Do not set a literal 'multipart/form-data' Content-Type: it has no boundary, which
    // breaks server-side parsing. Clearing the header lets the browser generate the correct
    // multipart boundary itself; this instance's default 'application/json' header would
    // otherwise make axios JSON-stringify the FormData instead of sending it as a file.
    const res = await apiClient.post(`/conversations/${conversationId}/attachments`, formData, {
      headers: {
        'Content-Type': undefined,
      },
    })
    return res.data
  },

  // Live Conversation Context Graph API
  async getContextGraph(conversationId) {
    const res = await apiClient.get(`/conversations/${conversationId}/context-graph`)
    return res.data
  },

  async dismissInconsistency(conversationId, inconsistencyId) {
    const res = await apiClient.post(`/conversations/${conversationId}/context-graph/inconsistencies/${inconsistencyId}/dismiss`)
    return res.data
  },

  async resolveInconsistency(conversationId, inconsistencyId, note = null) {
    const res = await apiClient.post(`/conversations/${conversationId}/context-graph/inconsistencies/${inconsistencyId}/resolve`, { note })
    return res.data
  },

  async resolveNode(conversationId, nodeId, status = 'completed', resolution_note = null) {
    const res = await apiClient.post(`/conversations/${conversationId}/context-graph/nodes/${nodeId}/resolve`, { status, resolution_note })
    return res.data
  },
}
