import { apiClient } from './apiClient'

export const groupService = {
  async createGroup(title, initialMemberUsernames = []) {
    const res = await apiClient.post('/groups', {
      title,
      initial_member_usernames: initialMemberUsernames.length > 0 ? initialMemberUsernames : null,
    })
    return res.data
  },

  async listGroups() {
    const res = await apiClient.get('/groups')
    return res.data
  },

  async getGroup(groupId) {
    const res = await apiClient.get(`/groups/${groupId}`)
    return res.data
  },

  async getMembers(groupId) {
    const res = await apiClient.get(`/groups/${groupId}/members`)
    return res.data
  },

  async createInvitation(groupId, { maxUses = null, expiresInDays = 7 } = {}) {
    const res = await apiClient.post(`/groups/${groupId}/invitations`, {
      max_uses: maxUses ? parseInt(maxUses, 10) : null,
      expires_in_days: expiresInDays ? parseInt(expiresInDays, 10) : 7,
    })
    return res.data
  },

  async revokeInvitation(groupId, invitationId) {
    const res = await apiClient.delete(`/groups/${groupId}/invitations/${invitationId}`)
    return res.data
  },

  async removeMember(groupId, userId) {
    const res = await apiClient.delete(`/groups/${groupId}/members/${userId}`)
    return res.data
  },

  async promoteMember(groupId, userId) {
    const res = await apiClient.post(`/groups/${groupId}/members/${userId}/promote`)
    return res.data
  },

  async leaveGroup(groupId) {
    const res = await apiClient.post(`/groups/${groupId}/leave`)
    return res.data
  },

  async uploadGroupAvatar(groupId, file) {
    const formData = new FormData()
    formData.append('file', file)
    // apiClient defaults Content-Type to 'application/json'; that default must be explicitly
    // cleared for FormData uploads or axios JSON-stringifies the body instead of sending it
    // as a file (see authService.uploadAvatar for the full explanation).
    const res = await apiClient.post(`/groups/${groupId}/avatar`, formData, {
      headers: { 'Content-Type': undefined },
    })
    return res.data
  },

  async removeGroupAvatar(groupId) {
    const res = await apiClient.delete(`/groups/${groupId}/avatar`)
    return res.data
  },
}
