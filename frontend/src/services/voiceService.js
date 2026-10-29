import { apiClient } from './apiClient'

export const SUPPORTED_VOICE_LANGUAGES = [
  { code: 'en', name: 'English' },
  { code: 'es', name: 'Spanish' },
  { code: 'fr', name: 'French' },
  { code: 'de', name: 'German' },
  { code: 'hi', name: 'Hindi' },
  { code: 'zh', name: 'Chinese' },
  { code: 'ja', name: 'Japanese' },
  { code: 'ar', name: 'Arabic' },
  { code: 'pt', name: 'Portuguese' },
  { code: 'ru', name: 'Russian' },
  { code: 'it', name: 'Italian' },
  { code: 'ko', name: 'Korean' },
  { code: 'nl', name: 'Dutch' },
  { code: 'tr', name: 'Turkish' },
]

export const voiceService = {
  /**
   * Upload recorded audio blob as a voice note.
   */
  async uploadVoiceNote(conversationId, audioBlob, duration, clientId = null, replyToMessageId = null) {
    const formData = new FormData()
    // Default extension webm, or check blob type
    const filename = audioBlob.type?.includes('ogg') ? 'recording.ogg' : 'recording.webm'
    formData.append('file', audioBlob, filename)
    formData.append('duration', String(duration))
    if (clientId) formData.append('client_id', clientId)
    if (replyToMessageId) formData.append('reply_to_message_id', replyToMessageId)

    // See conversationService.uploadAttachment for why this must be `undefined`, not a
    // literal 'multipart/form-data' string (no boundary -> broken upload either way).
    const res = await apiClient.post(`/conversations/${conversationId}/voice`, formData, {
      headers: {
        'Content-Type': undefined,
      },
    })
    return res.data
  },

  /**
   * Request translation for an existing voice note transcript.
   */
  async translateVoiceNote(conversationId, messageId, targetLanguage) {
    const res = await apiClient.post(`/conversations/${conversationId}/messages/${messageId}/translate`, {
      target_language: targetLanguage,
    })
    return res.data
  },

  /**
   * Retry transcription when failed or consent was granted.
   */
  async retryTranscription(conversationId, messageId) {
    const res = await apiClient.post(`/conversations/${conversationId}/messages/${messageId}/retry-transcription`)
    return res.data
  },
}
