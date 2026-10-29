import React from 'react'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { MeetingInvitationCard } from '../components/chat/MeetingInvitationCard'
import { VoiceMessagePlayer } from '../components/chat/VoiceMessagePlayer'
import { ConversationHeader } from '../components/layout/ConversationHeader'
import { MessageComposer } from '../components/chat/MessageComposer'
import { meetingService } from '../services/meetingService'
import { voiceService } from '../services/voiceService'

// Mock services
vi.mock('../services/meetingService', () => ({
  meetingService: {
    createMeeting: vi.fn(),
    getAuthUrl: vi.fn(),
    connectGoogleMeet: vi.fn(),
  },
}))

vi.mock('../services/voiceService', () => ({
  voiceService: {
    uploadVoiceNote: vi.fn(),
    translateVoiceNote: vi.fn(),
    retryTranscription: vi.fn(),
    SUPPORTED_VOICE_LANGUAGES: [
      { code: 'es', name: 'Spanish' },
      { code: 'fr', name: 'French' },
      { code: 'de', name: 'German' },
      { code: 'ta', name: 'Tamil' },
      { code: 'hi', name: 'Hindi' },
    ],
  },
  SUPPORTED_VOICE_LANGUAGES: [
    { code: 'es', name: 'Spanish' },
    { code: 'fr', name: 'French' },
    { code: 'de', name: 'German' },
    { code: 'ta', name: 'Tamil' },
    { code: 'hi', name: 'Hindi' },
  ],
}))

vi.mock('../services/authService', () => ({
  authService: {
    getCurrentUser: vi.fn().mockResolvedValue({ id: 'usr-self', username: 'alice', email: 'alice@example.com' }),
    getUserPreferences: vi.fn().mockResolvedValue({ ai_consent: true, ai_draft_analysis: true, ai_autocomplete: true }),
    updateUserPreferences: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('../services/aiService', () => ({
  aiService: {
    analyzeDraft: vi.fn().mockResolvedValue({
      corrected_text: null,
      corrections: [],
      completions: [],
      ambiguity_detected: false,
    }),
    getRecommendations: vi.fn().mockResolvedValue([]),
    checkAlignment: vi.fn().mockResolvedValue({ findings: [] }),
    getAiItems: vi.fn().mockResolvedValue({ findings: [], recommendations: [] }),
  },
}))

vi.mock('../context/AuthContext', () => ({
  useAuth: () => ({
    user: { id: 'usr-self', username: 'alice', email: 'alice@example.com' },
    isAuthenticated: true,
  }),
  AuthProvider: ({ children }) => children,
}))

const mockSendVoiceNote = vi.fn().mockResolvedValue({})
const mockSetReplyTo = vi.fn()
const mockTriggerAlignment = vi.fn()
const mockRequestRecommendations = vi.fn()

vi.mock('../context/ChatContext', () => ({
  useChat: () => ({
    socketStatus: 'connected',
    activeConversationId: 'conv-test',
    conversations: [],
    replyTo: null,
    setReplyTo: mockSetReplyTo,
    sendVoiceNote: mockSendVoiceNote,
    triggerAlignment: mockTriggerAlignment,
    requestRecommendations: mockRequestRecommendations,
  }),
  ChatProvider: ({ children }) => children,
}))

describe('Feature One: Google Meet REST API UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('ar_access_token', 'mock-test-token')
  })

  it('renders MeetingInvitationCard with valid Google Meet URI, Join link and Copy button', async () => {
    const mockClipboard = {
      writeText: vi.fn().mockResolvedValue(undefined),
    }
    Object.assign(navigator, { clipboard: mockClipboard })

    const metadata = {
      meeting_uri: 'https://meet.google.com/abc-defg-hij',
      meeting_code: 'abc-defg-hij',
      creator_username: 'alice',
    }

    render(<MeetingInvitationCard metadata={metadata} isOwn={false} />)

    expect(screen.getByTestId('meeting-invitation-card')).toBeInTheDocument()
    expect(screen.getByText('Google Meet Call')).toBeInTheDocument()
    expect(screen.getByText('Started by @alice')).toBeInTheDocument()
    expect(screen.getByText('abc-defg-hij')).toBeInTheDocument()

    const joinBtn = screen.getByTestId('join-meeting-btn')
    expect(joinBtn).toHaveAttribute('href', 'https://meet.google.com/abc-defg-hij')
    expect(joinBtn).toHaveAttribute('target', '_blank')
    expect(joinBtn).toHaveAttribute('rel', 'noopener noreferrer')

    const copyBtn = screen.getByTestId('copy-meeting-link-btn')
    fireEvent.click(copyBtn)

    expect(mockClipboard.writeText).toHaveBeenCalledWith('https://meet.google.com/abc-defg-hij')
    await waitFor(() => {
      expect(screen.getByText('Copied')).toBeInTheDocument()
    })
  })

  it('handles missing or empty meeting URI in MeetingInvitationCard safely', () => {
    render(<MeetingInvitationCard metadata={{}} isOwn={false} />)
    expect(screen.getByText('Link unavailable')).toBeInTheDocument()
    expect(screen.getByTestId('copy-meeting-link-btn')).toBeDisabled()
  })

  it('triggers meeting creation from ConversationHeader Call button', async () => {
    meetingService.createMeeting.mockResolvedValueOnce({
      requires_auth: false,
      meeting_uri: 'https://meet.google.com/xyz-uvwx-rst',
      meeting_code: 'xyz-uvwx-rst',
      invitation: { meeting_uri: 'https://meet.google.com/xyz-uvwx-rst' },
    })

    const mockConversation = {
      id: 'conv-123',
      is_group: false,
      other_participant: { id: 'usr-bob', username: 'bob', display_name: 'Bob Partner' },
    }

    render(<ConversationHeader conversation={mockConversation} onToggleSidebar={() => {}} />)

    const callBtn = screen.getByTestId('header-call-btn')
    expect(callBtn).toBeInTheDocument()

    fireEvent.click(callBtn)

    await waitFor(() => {
      expect(meetingService.createMeeting).toHaveBeenCalledWith('conv-123', expect.any(String))
    })
  })

  it('redirects to Google OAuth when createMeeting returns requires_auth: true', async () => {
    const originalLocation = window.location
    delete window.location
    window.location = { href: '' }

    meetingService.createMeeting.mockResolvedValueOnce({
      requires_auth: true,
      authorization_url: 'https://accounts.google.com/o/oauth2/v2/auth?client_id=test',
    })

    const mockConversation = {
      id: 'conv-group-456',
      is_group: true,
      title: 'Engineering Alignment',
      member_count: 5,
    }

    render(<ConversationHeader conversation={mockConversation} onToggleSidebar={() => {}} />)

    const callBtn = screen.getByTestId('header-call-btn')
    fireEvent.click(callBtn)

    await waitFor(() => {
      expect(window.location.href).toBe('https://accounts.google.com/o/oauth2/v2/auth?client_id=test')
    })

    window.location = originalLocation
  })

  it('displays error banner and retry button when meeting creation fails', async () => {
    meetingService.createMeeting.mockRejectedValueOnce(new Error('Provider rate limit reached'))

    const mockConversation = {
      id: 'conv-789',
      is_group: false,
      other_participant: { id: 'usr-carol', username: 'carol', display_name: 'Carol' },
    }

    render(<ConversationHeader conversation={mockConversation} onToggleSidebar={() => {}} />)

    const callBtn = screen.getByTestId('header-call-btn')
    fireEvent.click(callBtn)

    await waitFor(() => {
      expect(screen.getByTestId('call-error-banner')).toBeInTheDocument()
      expect(screen.getByText(/Provider rate limit reached/i)).toBeInTheDocument()
      expect(screen.getByText('Retry')).toBeInTheDocument()
    })
  })
})

describe('Feature Two: Voice Messages UI, Playback, and Translation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('ar_access_token', 'mock-test-token')
  })

  it('renders VoiceMessagePlayer with audio duration and waveform', () => {
    const mockMessage = {
      id: 'msg-voice-1',
      conversation_id: 'conv-100',
      content: '',
      message_type: 'voice_note',
      attachments: [
        {
          id: 'att-voice-1',
          content_type: 'audio/webm',
          original_filename: 'voice_note.webm',
        },
      ],
      voice_transcript: {
        id: 'vt-1',
        duration_seconds: 14,
        transcription_status: 'completed',
        source_language: 'en',
        transcript_text: 'Let us coordinate on the Q4 alignment plan tomorrow.',
        translations: {},
      },
    }

    render(<VoiceMessagePlayer message={mockMessage} isOwn={false} />)

    expect(screen.getByTestId('voice-message-player')).toBeInTheDocument()
    expect(screen.getByTestId('voice-play-pause-btn')).toBeInTheDocument()
    expect(screen.getByText('0:14')).toBeInTheDocument()
    expect(screen.getByText('Transcribed (EN)')).toBeInTheDocument()
  })

  it('expands transcript drawer, displays text, and performs multilingual translation', async () => {
    voiceService.translateVoiceNote.mockResolvedValueOnce({
      source_language: 'en',
      target_language: 'es',
      translated_text: 'Coordinemos el plan de alineacion del cuarto trimestre manana.',
      provider: 'verified-groq-gpt-oss',
      cached: false,
    })

    const mockMessage = {
      id: 'msg-voice-2',
      conversation_id: 'conv-100',
      content: '',
      message_type: 'voice_note',
      attachments: [{ id: 'att-2', content_type: 'audio/webm' }],
      voice_transcript: {
        id: 'vt-2',
        duration_seconds: 22,
        transcription_status: 'completed',
        source_language: 'en',
        transcript_text: 'We should verify alignment before publishing.',
        translations: {
          es: {
            text: 'Debemos verificar la alineacion antes de publicar.',
            provider: 'verified-llm',
          },
        },
      },
    }

    render(<VoiceMessagePlayer message={mockMessage} isOwn={true} />)

    // Open transcript drawer
    const toggleBtn = screen.getByTestId('toggle-transcript-btn')
    fireEvent.click(toggleBtn)

    expect(screen.getByTestId('transcript-drawer')).toBeInTheDocument()
    expect(screen.getByTestId('original-transcript-text')).toHaveTextContent(
      'We should verify alignment before publishing.'
    )

    // Check cached translation in Spanish is already visible
    expect(screen.getByTestId('translated-transcript-text')).toHaveTextContent(
      'Debemos verificar la alineacion antes de publicar.'
    )

    // Change target language to French
    const langSelect = screen.getByTestId('voice-target-lang-select')
    fireEvent.change(langSelect, { target: { value: 'fr' } })

    // Click translate
    const translateBtn = screen.getByTestId('voice-translate-btn')
    fireEvent.click(translateBtn)

    await waitFor(() => {
      expect(voiceService.translateVoiceNote).toHaveBeenCalledWith('conv-100', 'msg-voice-2', 'fr')
    })
  })

  it('renders failed transcription state with retry action', async () => {
    voiceService.retryTranscription.mockResolvedValueOnce({ status: 'queued' })

    const mockMessage = {
      id: 'msg-voice-3',
      conversation_id: 'conv-100',
      content: '',
      message_type: 'voice_note',
      attachments: [{ id: 'att-3', content_type: 'audio/webm' }],
      voice_transcript: {
        id: 'vt-3',
        duration_seconds: 5,
        transcription_status: 'failed',
      },
    }

    render(<VoiceMessagePlayer message={mockMessage} isOwn={false} />)

    expect(screen.getByText('Transcription failed')).toBeInTheDocument()
    const retryBtn = screen.getByRole('button', { name: /retry/i })
    fireEvent.click(retryBtn)

    await waitFor(() => {
      expect(voiceService.retryTranscription).toHaveBeenCalledWith('conv-100', 'msg-voice-3')
    })
  })
})

describe('Feature Two: MessageComposer Microphone & Recording', () => {
  let mockStream

  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('ar_access_token', 'mock-test-token')

    mockStream = {
      getTracks: vi.fn().mockReturnValue([
        { stop: vi.fn() },
      ]),
    }

    Object.defineProperty(navigator, 'mediaDevices', {
      value: {
        getUserMedia: vi.fn().mockResolvedValue(mockStream),
      },
      writable: true,
      configurable: true,
    })

    // Mock MediaRecorder with standard constructor
    function MockMediaRecorder(stream, options) {
      this.stream = stream
      this.options = options
      this.state = 'recording'
      this.ondataavailable = null
      this.onstop = null
    }
    MockMediaRecorder.prototype.start = vi.fn()
    MockMediaRecorder.prototype.stop = vi.fn(function () {
      this.state = 'inactive'
      if (this.onstop) this.onstop()
    })
    MockMediaRecorder.isTypeSupported = vi.fn().mockReturnValue(true)
    global.MediaRecorder = MockMediaRecorder

    // Mock Audio
    function MockAudio() {}
    MockAudio.prototype.play = vi.fn().mockResolvedValue(undefined)
    MockAudio.prototype.pause = vi.fn()
    MockAudio.prototype.addEventListener = vi.fn()
    MockAudio.prototype.removeEventListener = vi.fn()
    global.Audio = MockAudio

    // Mock URL.createObjectURL & revokeObjectURL
    if (!global.URL.createObjectURL) {
      global.URL.createObjectURL = vi.fn().mockReturnValue('blob:mock-audio-url')
      global.URL.revokeObjectURL = vi.fn()
    }
  })

  it('renders microphone button and opens recording dock on click', async () => {
    const onSend = vi.fn()

    render(
      <MessageComposer
        onSend={onSend}
      />
    )

    const micBtn = screen.getByTestId('composer-mic-btn')
    expect(micBtn).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(micBtn)
    })

    await waitFor(() => {
      expect(navigator.mediaDevices.getUserMedia).toHaveBeenCalledWith({ audio: true })
      expect(screen.getByTestId('voice-recording-dock')).toBeInTheDocument()
      expect(screen.getByTestId('stop-review-recording-btn')).toBeInTheDocument()
    })

    // Discard recording
    const discardBtn = screen.getByTestId('discard-recording-btn')
    fireEvent.click(discardBtn)

    await waitFor(() => {
      expect(screen.queryByTestId('voice-recording-dock')).not.toBeInTheDocument()
      expect(mockStream.getTracks()[0].stop).toHaveBeenCalled()
    })
  })

  it('handles microphone permission denial gracefully without breaking composer', async () => {
    navigator.mediaDevices.getUserMedia.mockRejectedValueOnce({
      name: 'NotAllowedError',
      message: 'Permission denied by user',
    })

    render(
      <MessageComposer
        onSend={vi.fn()}
      />
    )

    const micBtn = screen.getByTestId('composer-mic-btn')
    await act(async () => {
      fireEvent.click(micBtn)
    })

    await waitFor(() => {
      expect(screen.getByTestId('mic-permission-error')).toBeInTheDocument()
      expect(screen.getByText(/Microphone permission was denied/i)).toBeInTheDocument()
    })

    // Normal text message composer is still intact and functional
    expect(screen.getByPlaceholderText('Message or ask for alignment...')).toBeInTheDocument()
  })
})
