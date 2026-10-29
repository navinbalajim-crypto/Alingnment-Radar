import { describe, it, expect, vi, beforeEach } from 'vitest'
import { apiClient, setTokens } from '../services/apiClient'
import { authService } from '../services/authService'
import { groupService } from '../services/groupService'
import { conversationService } from '../services/conversationService'
import { voiceService } from '../services/voiceService'

// Regression tests for a real, confirmed bug: `apiClient` sets a default
// 'Content-Type: application/json' header. Axios's own transformRequest (see
// node_modules/axios/lib/defaults/index.js) JSON-stringifies any FormData body when the
// resolved Content-Type still says 'application/json' -- silently destroying every file
// upload (avatars, attachments, voice notes) without throwing an error. A literal
// 'Content-Type: multipart/form-data' string is just as broken (no boundary). These tests
// run the REAL axios request pipeline (not a mock of our own code) by substituting a custom
// adapter that inspects `config.data`/`config.headers` exactly as axios would hand them to
// the browser, i.e. strictly after axios's real `transformRequest` has already run.

function captureAdapter(onCapture) {
  return (config) => {
    onCapture(config)
    return Promise.resolve({ data: {}, status: 200, statusText: 'OK', headers: {}, config })
  }
}

describe('FormData uploads survive axios\'s default JSON Content-Type', () => {
  beforeEach(() => {
    setTokens('test-jwt-token', 'test-refresh-token')
  })

  async function assertSurvivesRealAxios(doUpload) {
    let captured = null
    const originalAdapter = apiClient.defaults.adapter
    apiClient.defaults.adapter = captureAdapter((config) => {
      captured = config
    })
    try {
      await doUpload()
    } finally {
      apiClient.defaults.adapter = originalAdapter
    }

    expect(captured).not.toBeNull()
    // The real bug: axios turning the body into a JSON string instead of leaving it as
    // FormData. If this fails, the backend receives '{"file":...}' instead of a file.
    expect(captured.data instanceof FormData).toBe(true)
    // A literal 'multipart/form-data' with no boundary is equally broken server-side.
    const contentType = captured.headers?.getContentType?.() ?? captured.headers?.['Content-Type']
    if (contentType) {
      expect(contentType.toLowerCase()).not.toBe('application/json')
      if (/^multipart\/form-data/i.test(contentType)) {
        expect(contentType).toMatch(/boundary=/i)
      }
    }
    return captured
  }

  it('authService.uploadAvatar sends real multipart data, not JSON-stringified FormData', async () => {
    const file = new File(['fake-image-bytes'], 'me.png', { type: 'image/png' })
    await assertSurvivesRealAxios(() => authService.uploadAvatar(file).catch(() => {}))
  })

  it('groupService.uploadGroupAvatar sends real multipart data, not JSON-stringified FormData', async () => {
    const file = new File(['fake-image-bytes'], 'group.png', { type: 'image/png' })
    await assertSurvivesRealAxios(() => groupService.uploadGroupAvatar('grp-1', file).catch(() => {}))
  })

  it('conversationService.uploadAttachment sends real multipart data, not JSON-stringified FormData', async () => {
    const file = new File(['fake-doc-bytes'], 'doc.pdf', { type: 'application/pdf' })
    await assertSurvivesRealAxios(() => conversationService.uploadAttachment('conv-1', file).catch(() => {}))
  })

  it('voiceService.uploadVoiceNote sends real multipart data, not JSON-stringified FormData', async () => {
    const blob = new Blob(['fake-audio-bytes'], { type: 'audio/webm' })
    await assertSurvivesRealAxios(() => voiceService.uploadVoiceNote('conv-1', blob, 3).catch(() => {}))
  })

  it('sanity check: this test harness actually detects the bug when it is reintroduced', async () => {
    // Proves the assertion above is not a false-positive by deliberately reproducing the
    // exact historical bug (apiClient's JSON default left in place for a FormData body).
    let captured = null
    const originalAdapter = apiClient.defaults.adapter
    apiClient.defaults.adapter = captureAdapter((config) => {
      captured = config
    })
    try {
      const formData = new FormData()
      formData.append('file', new File(['x'], 'x.png', { type: 'image/png' }))
      await apiClient.post('/users/me/avatar', formData) // no Content-Type override -- the bug
    } finally {
      apiClient.defaults.adapter = originalAdapter
    }
    expect(captured.data instanceof FormData).toBe(false)
    expect(typeof captured.data).toBe('string') // JSON-stringified -- this is the broken behaviour
  })
})
