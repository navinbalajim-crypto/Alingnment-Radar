import { apiClient } from './apiClient'

export const reminderService = {
  async extractTask(conversationId, text, timezone = 'Asia/Kolkata') {
    const res = await apiClient.post(`/conversations/${conversationId}/reminders/extract`, {
      text,
      timezone,
    })
    return res.data
  },

  async listReminders(conversationId) {
    const res = await apiClient.get(`/conversations/${conversationId}/reminders`)
    return res.data
  },

  async createReminder(conversationId, reminderData) {
    const res = await apiClient.post(`/conversations/${conversationId}/reminders`, reminderData)
    return res.data
  },

  async updateReminder(reminderId, updateData) {
    const res = await apiClient.patch(`/reminders/${reminderId}`, updateData)
    return res.data
  },

  async listNotifications({ unreadOnly = false } = {}) {
    const res = await apiClient.get('/notifications', {
      params: { unread_only: unreadOnly },
    })
    return res.data
  },

  async markNotificationRead(notificationId) {
    const res = await apiClient.patch(`/notifications/${notificationId}/read`)
    return res.data
  },
}
