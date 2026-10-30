import React, { useState, useRef, useEffect } from 'react'
import {
  Play,
  Pause,
  Volume2,
  Languages,
  ChevronDown,
  ChevronUp,
  RotateCw,
  Loader2,
  AlertCircle,
  Check,
  Globe,
} from 'lucide-react'
import { voiceService, SUPPORTED_VOICE_LANGUAGES } from '../../services/voiceService'
import { cn, resolveApiUrl } from '../../utils/helpers'

function formatSeconds(secs) {
  if (isNaN(secs) || secs < 0) return '0:00'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

export function VoiceMessagePlayer({ message, isOwn }) {
  const transcript = message.voice_transcript || null
  const originalText = transcript?.transcript_text || ''
  const status = transcript?.transcription_status || 'uploaded'
  const sourceLang = transcript?.source_language || 'en'
  const translations = transcript?.translations || {}

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(
    transcript?.duration_seconds || message.msg_metadata?.duration_seconds || 0
  )
  const [showTranscript, setShowTranscript] = useState(Boolean(originalText))
  const [selectedLanguage, setSelectedLanguage] = useState('es')
  const [isTranslating, setIsTranslating] = useState(false)
  const [isRetrying, setIsRetrying] = useState(false)
  const [translationError, setTranslationError] = useState(null)

  const audioRef = useRef(null)

  useEffect(() => {
    if (originalText) {
      setShowTranscript(true)
    }
  }, [originalText])

  useEffect(() => {
    const d = transcript?.duration_seconds || message.msg_metadata?.duration_seconds || 0
    if (d > 0) setDuration(d)
  }, [transcript?.duration_seconds, message.msg_metadata?.duration_seconds])

  // Find audio attachment
  const attachments = Array.isArray(message.attachments) ? message.attachments : []
  const audioAttachment =
    attachments.find(
      (att) =>
        att.content_type?.startsWith('audio/') ||
        att.original_filename?.endsWith('.webm') ||
        att.original_filename?.endsWith('.ogg') ||
        att.original_filename?.endsWith('.wav') ||
        att.original_filename?.endsWith('.mp3') ||
        att.original_filename?.endsWith('.m4a')
    ) || attachments[0]

  const attachmentId =
    audioAttachment?.id ||
    message.voice_transcript?.attachment_id ||
    message.msg_metadata?.attachment_id ||
    null

  const token = (typeof localStorage !== 'undefined' && localStorage.getItem('ar_access_token')) || ''
  const audioSrc = attachmentId
    ? resolveApiUrl(
        `/api/v1/conversations/${message.conversation_id}/attachments/${attachmentId}${
          token ? `?token=${encodeURIComponent(token)}` : ''
        }`
      )
    : null

  const activeTranslation = translations[selectedLanguage] || null

  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) {
      audioRef.current.pause()
    } else {
      audioRef.current.play().catch((err) => console.warn('Audio playback prevented:', err))
    }
  }

  const handleTimeUpdate = () => {
    if (audioRef.current) {
      setCurrentTime(audioRef.current.currentTime)
    }
  }

  const handleLoadedMetadata = () => {
    if (audioRef.current && (!duration || isNaN(duration))) {
      setDuration(audioRef.current.duration)
    }
  }

  const handleEnded = () => {
    setIsPlaying(false)
    setCurrentTime(0)
  }

  const handleSeek = (e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const clickX = e.clientX - rect.left
    const percent = Math.max(0, Math.min(1, clickX / rect.width))
    const newTime = percent * (duration || 1)
    if (audioRef.current) {
      audioRef.current.currentTime = newTime
      setCurrentTime(newTime)
    }
  }

  const handleTranslate = async () => {
    if (!transcript || isTranslating) return
    setIsTranslating(true)
    setTranslationError(null)
    try {
      await voiceService.translateVoiceNote(message.conversation_id, message.id, selectedLanguage)
    } catch (err) {
      console.error('Translation request failed:', err)
      setTranslationError(err.response?.data?.message || err.message || 'Translation failed')
    } finally {
      setIsTranslating(false)
    }
  }

  const handleRetryTranscription = async () => {
    if (isRetrying) return
    setIsRetrying(true)
    try {
      await voiceService.retryTranscription(message.conversation_id, message.id)
    } catch (err) {
      console.error('Retry transcription failed:', err)
    } finally {
      setIsRetrying(false)
    }
  }

  const progressPercent = duration > 0 ? (currentTime / duration) * 100 : 0

  // 24 waveform bar heights
  const waveformHeights = [
    30, 45, 75, 55, 90, 60, 35, 80, 100, 70, 40, 65,
    85, 95, 50, 40, 60, 80, 100, 65, 45, 30, 50, 40
  ]

  return (
    <div
      className={cn(
        'w-full max-w-sm rounded-2xl p-3.5 border transition-all text-neutral-900 dark:text-neutral-100',
        isOwn
          ? 'bg-apple-blue/10 dark:bg-apple-blue/20 border-apple-blue/30'
          : 'bg-white dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700'
      )}
      data-testid="voice-message-player"
    >
      {audioSrc && (
        <audio
          ref={audioRef}
          src={audioSrc}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onTimeUpdate={handleTimeUpdate}
          onLoadedMetadata={handleLoadedMetadata}
          onEnded={handleEnded}
          preload="metadata"
          className="hidden"
        />
      )}

      {/* Main player controls: Play/Pause, Waveform, Timers */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={togglePlay}
          disabled={!audioSrc}
          className={cn(
            'w-10 h-10 rounded-full flex items-center justify-center shrink-0 shadow-sm transition-transform active:scale-95 disabled:opacity-50',
            isOwn
              ? 'bg-apple-blue text-white hover:bg-blue-600'
              : 'bg-neutral-900 dark:bg-white text-white dark:text-neutral-900 hover:opacity-90'
          )}
          title={isPlaying ? 'Pause' : 'Play voice message'}
          aria-label={isPlaying ? 'Pause' : 'Play'}
          data-testid="voice-play-pause-btn"
        >
          {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
        </button>

        {/* Waveform Scrubber */}
        <div className="flex-1 min-w-0">
          <div
            onClick={handleSeek}
            className="h-8 flex items-center gap-[2.5px] cursor-pointer py-1 group"
            title="Click to seek"
            role="progressbar"
            aria-valuenow={Math.round(progressPercent)}
            aria-valuemin="0"
            aria-valuemax="100"
          >
            {waveformHeights.map((h, i) => {
              const barPercent = (i / waveformHeights.length) * 100
              const isFilled = barPercent <= progressPercent
              return (
                <div
                  key={i}
                  style={{ height: `${h}%` }}
                  className={cn(
                    'w-1 rounded-full transition-colors duration-150',
                    isFilled
                      ? isOwn
                        ? 'bg-apple-blue dark:bg-blue-400'
                        : 'bg-neutral-900 dark:bg-white'
                      : 'bg-black/15 dark:bg-white/20 group-hover:bg-black/25 dark:group-hover:bg-white/30'
                  )}
                />
              )
            })}
          </div>

          <div className="flex items-center justify-between text-[11px] text-neutral-500 dark:text-neutral-400 font-mono mt-0.5">
            <span>{formatSeconds(currentTime)}</span>
            <span>{formatSeconds(duration)}</span>
          </div>
        </div>
      </div>

      {/* Transcription & Translation Section */}
      <div className="mt-2.5 pt-2 border-t border-black/[0.06] dark:border-white/[0.08]">
        <div className="flex items-center justify-between gap-2">
          {/* Status Indicator */}
          <div className="flex items-center gap-1.5 text-xs text-neutral-600 dark:text-neutral-300">
            {status === 'processing' && (
              <span className="flex items-center gap-1 text-apple-blue font-medium text-[11px]">
                <Loader2 className="w-3 h-3 animate-spin" />
                Transcribing...
              </span>
            )}
            {status === 'uploaded' && (
              <span className="text-neutral-400 text-[11px]">Queued for transcription</span>
            )}
            {status === 'completed' && (
              <span className="flex items-center gap-1 text-emerald-600 dark:text-emerald-400 font-medium text-[11px]">
                <Check className="w-3 h-3" />
                Transcribed ({sourceLang.toUpperCase()})
              </span>
            )}
            {status === 'failed' && (
              <span className="flex items-center gap-1 text-red-500 font-medium text-[11px]">
                <AlertCircle className="w-3 h-3" />
                Transcription failed
              </span>
            )}
            {status === 'consent_required' && (
              <span className="flex items-center gap-1 text-amber-500 font-medium text-[11px]">
                <AlertCircle className="w-3 h-3" />
                AI consent required
              </span>
            )}
          </div>

          <div className="flex items-center gap-1">
            {status === 'failed' && (
              <button
                type="button"
                onClick={handleRetryTranscription}
                disabled={isRetrying}
                className="px-2 py-0.5 rounded text-[11px] font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 flex items-center gap-1"
                title="Retry transcription"
              >
                <RotateCw className={`w-3 h-3 ${isRetrying ? 'animate-spin' : ''}`} />
                <span>Retry</span>
              </button>
            )}

            {status === 'completed' && (
              <button
                type="button"
                onClick={() => setShowTranscript((prev) => !prev)}
                className="px-2 py-0.5 rounded text-[11px] font-medium text-apple-blue hover:bg-blue-50 dark:hover:bg-blue-950/40 flex items-center gap-1 transition-colors"
                data-testid="toggle-transcript-btn"
              >
                <span>{showTranscript ? 'Hide text' : 'Transcript'}</span>
                {showTranscript ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
              </button>
            )}
          </div>
        </div>

        {/* Expandable Transcript & Multilingual Translation Drawer */}
        {showTranscript && status === 'completed' && (
          <div
            className="mt-2.5 p-2.5 rounded-xl bg-black/[0.03] dark:bg-white/[0.04] border border-black/[0.04] dark:border-white/[0.04] text-xs space-y-2.5 animate-in fade-in duration-150"
            data-testid="transcript-drawer"
          >
            {/* Original transcript */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-neutral-400">
                  Original ({sourceLang.toUpperCase()})
                </span>
              </div>
              <p className="text-neutral-800 dark:text-neutral-200 leading-relaxed font-sans" data-testid="original-transcript-text">
                {originalText}
              </p>
            </div>

            {/* Translation controls */}
            <div className="pt-2 border-t border-black/[0.04] dark:border-white/[0.04]">
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-neutral-400">
                  <Languages className="w-3 h-3" />
                  <span>Translate</span>
                </div>

                <div className="flex items-center gap-1.5">
                  <select
                    value={selectedLanguage}
                    onChange={(e) => setSelectedLanguage(e.target.value)}
                    className="px-2 py-1 rounded-lg text-xs bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 text-neutral-800 dark:text-neutral-200 focus:outline-none focus:ring-1 focus:ring-apple-blue"
                    data-testid="voice-target-lang-select"
                  >
                    {SUPPORTED_VOICE_LANGUAGES.map((l) => (
                      <option key={l.code} value={l.code}>
                        {l.name} ({l.code})
                      </option>
                    ))}
                  </select>

                  <button
                    type="button"
                    onClick={handleTranslate}
                    disabled={isTranslating}
                    className="px-2.5 py-1 rounded-lg bg-apple-blue text-white text-xs font-medium hover:bg-blue-600 disabled:opacity-50 flex items-center gap-1 shadow-subtle"
                    data-testid="voice-translate-btn"
                  >
                    {isTranslating ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <Globe className="w-3 h-3" />
                    )}
                    <span>{activeTranslation ? 'Retranslate' : 'Translate'}</span>
                  </button>
                </div>
              </div>

              {translationError && (
                <p className="text-[11px] text-red-500 italic mb-1">{translationError}</p>
              )}

              {/* Display translated text */}
              {activeTranslation && (
                <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-neutral-900 dark:text-neutral-100 mt-1">
                  <div className="flex items-center justify-between mb-1 text-[10px] text-emerald-700 dark:text-emerald-400 font-semibold uppercase">
                    <span>Translated to {selectedLanguage.toUpperCase()}</span>
                    <span className="font-normal opacity-70">
                      {activeTranslation.provider || 'verified'}
                    </span>
                  </div>
                  <p className="leading-relaxed" data-testid="translated-transcript-text">
                    {activeTranslation.text}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
