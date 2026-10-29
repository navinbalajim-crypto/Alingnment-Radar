import React, { useState, useRef, useEffect, useLayoutEffect, forwardRef, useImperativeHandle, useCallback, useMemo } from 'react'
import { Button } from '../ui/Button'
import { ArrowUp, WifiOff, RefreshCw, Sparkles, Check, X, ChevronRight, Loader2, Wand2, Music, Video, AlertCircle, AlertTriangle, Paperclip, FileText, Image as ImageIcon, Reply, Mic, Trash2, Play, Pause, Square } from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import { useDraftAssistant } from '../../hooks/useDraftAssistant'
import { useWritingSuggestions } from '../../hooks/useWritingSuggestions'
import { useAiPreferences } from '../../hooks/useAiPreferences'
import { MAX_SUGGESTIONS } from '../../utils/autocomplete'
import { getWordCorrection } from '../../utils/spellingEngine'
import { loadSpellingAssets } from '../../utils/spellChecker'
import { RecommendationCard } from '../ai/RecommendationCard'

const correctionKey = (c) => `${c.original}\u0000${c.corrected}`

function readFlag(name, fallback) {
  try {
    const stored = localStorage.getItem(name)
    return stored === null ? fallback : stored === 'true'
  } catch {
    return fallback
  }
}

function writeFlag(name, value) {
  try {
    localStorage.setItem(name, String(value))
  } catch {
    // storage unavailable: preference lasts for this session only
  }
}

function replaceFirst(text, original, corrected) {
  const idx = text.indexOf(original)
  if (idx === -1) return text
  return text.slice(0, idx) + corrected + text.slice(idx + original.length)
}

function formatSeconds(secs) {
  if (isNaN(secs) || secs < 0) return '0:00'
  const m = Math.floor(secs / 60)
  const s = Math.floor(secs % 60)
  return `${m}:${s < 10 ? '0' : ''}${s}`
}

export const MessageComposer = forwardRef(function MessageComposer(
  { onSend, disabled = false },
  ref
) {
  const { socketStatus, activeConversationId, conversations, replyTo, setReplyTo, sendVoiceNote } = useChat()
  const [content, setContent] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [recordingDuration, setRecordingDuration] = useState(0)
  const [audioBlob, setAudioBlob] = useState(null)
  const [audioUrl, setAudioUrl] = useState(null)
  const [isPlayingPreview, setIsPlayingPreview] = useState(false)
  const [micPermissionError, setMicPermissionError] = useState(null)
  const [isSendingVoice, setIsSendingVoice] = useState(false)

  const mediaRecorderRef = useRef(null)
  const mediaStreamRef = useRef(null)
  const recordingIntervalRef = useRef(null)
  const audioChunksRef = useRef([])
  const previewAudioRef = useRef(null)
  const [showCorrectionPreview, setShowCorrectionPreview] = useState(false)
  const [dismissedKeys, setDismissedKeys] = useState(() => new Set())
  // Draft text produced by accepting individual corrections; remaining suggestions stay valid for it.
  const [acceptedDraft, setAcceptedDraft] = useState(null)
  const [autoCorrectEnabled, setAutoCorrectEnabled] = useState(() => {
    try {
      const stored = localStorage.getItem('ar_autocorrect')
      // Auto-correct is enabled by default for unambiguous spelling mistakes
      return stored !== 'false'
    } catch {
      return true
    }
  })
  const [suggestEnabled, setSuggestEnabled] = useState(() => readFlag('ar_suggest', true))
  // Sending unsent drafts to external services is strictly opt-in, stored and enforced on the server.
  const { prefs: aiPrefs, error: prefsError, setPref } = useAiPreferences()
  const aiSuggestEnabled = aiPrefs.ai_autocomplete
  const [showPrivacy, setShowPrivacy] = useState(false)
  const [caret, setCaret] = useState(0)
  const [dismissedAt, setDismissedAt] = useState(null)
  const [nav, setNav] = useState({ sig: '', index: -1 })
  const [emptyWarning, setEmptyWarning] = useState(false)
  const [spellReady, setSpellReady] = useState(false)
  const textareaRef = useRef(null)
  // Caret to restore right after React commits the next value (never deferred to a later frame: a fast typist
  // would have moved on and the delayed restore would jump the caret back).
  const pendingSelection = useRef(null)
  const lastAutoCorrected = useRef(null)
  const undoneWords = useRef(new Set())

  const toggleAutoCorrect = useCallback(() => {
    setAutoCorrectEnabled((prev) => {
      const next = !prev
      try {
        localStorage.setItem('ar_autocorrect', String(next))
      } catch {}
      return next
    })
  }, [])

  // Cleanup audio tracks on unmount
  useEffect(() => {
    return () => {
      if (recordingIntervalRef.current) clearInterval(recordingIntervalRef.current)
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      }
      if (previewAudioRef.current) {
        previewAudioRef.current.pause()
      }
    }
  }, [])

  const startRecording = async () => {
    setMicPermissionError(null)
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setMicPermissionError('Audio recording is not supported in this browser.')
      return
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream

      let mimeType = 'audio/webm'
      if (typeof MediaRecorder !== 'undefined') {
        if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) {
          mimeType = 'audio/webm;codecs=opus'
        } else if (MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')) {
          mimeType = 'audio/ogg;codecs=opus'
        } else if (MediaRecorder.isTypeSupported('audio/mp4')) {
          mimeType = 'audio/mp4'
        }
      }

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder
      audioChunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          audioChunksRef.current.push(e.data)
        }
      }

      recorder.start(250)
      setIsRecording(true)
      setRecordingDuration(0)

      recordingIntervalRef.current = setInterval(() => {
        setRecordingDuration((prev) => prev + 1)
      }, 1000)
    } catch (err) {
      console.error('Microphone access denied or error:', err)
      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setMicPermissionError('Microphone permission was denied. Please allow microphone access in your browser settings.')
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setMicPermissionError('No microphone was found on this device.')
      } else {
        setMicPermissionError(`Microphone error: ${err.message || 'Unable to access microphone'}`)
      }
    }
  }

  const stopRecording = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current)
      recordingIntervalRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = () => {
        const mime = mediaRecorderRef.current?.mimeType || 'audio/webm'
        const blob = new Blob(audioChunksRef.current, { type: mime })
        setAudioBlob(blob)
        if (audioUrl) URL.revokeObjectURL(audioUrl)
        const url = URL.createObjectURL(blob)
        setAudioUrl(url)
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((track) => track.stop())
          mediaStreamRef.current = null
        }
      }
      mediaRecorderRef.current.stop()
    } else {
      if (mediaStreamRef.current) {
        mediaStreamRef.current.getTracks().forEach((track) => track.stop())
        mediaStreamRef.current = null
      }
    }
    setIsRecording(false)
  }

  const discardRecording = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current)
      recordingIntervalRef.current = null
    }
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = null
      try {
        mediaRecorderRef.current.stop()
      } catch {}
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }
    if (audioUrl) URL.revokeObjectURL(audioUrl)
    if (previewAudioRef.current) {
      previewAudioRef.current.pause()
      previewAudioRef.current = null
    }
    setIsRecording(false)
    setAudioBlob(null)
    setAudioUrl(null)
    setIsPlayingPreview(false)
    setRecordingDuration(0)
  }

  const togglePreviewPlay = () => {
    if (!audioUrl) return
    if (isPlayingPreview && previewAudioRef.current) {
      previewAudioRef.current.pause()
      setIsPlayingPreview(false)
    } else {
      if (!previewAudioRef.current) {
        previewAudioRef.current = new Audio(audioUrl)
        previewAudioRef.current.onended = () => setIsPlayingPreview(false)
      }
      previewAudioRef.current
        .play()
        .then(() => setIsPlayingPreview(true))
        .catch(() => {})
    }
  }

  const handleSendVoiceNote = async () => {
    if (!audioBlob || isSendingVoice || !sendVoiceNote) return
    setIsSendingVoice(true)
    try {
      await sendVoiceNote(audioBlob, Math.max(1, recordingDuration))
      discardRecording()
    } catch (err) {
      console.error('Failed to send voice note:', err)
    } finally {
      setIsSendingVoice(false)
    }
  }

  const stopRecordingAndSend = () => {
    if (recordingIntervalRef.current) {
      clearInterval(recordingIntervalRef.current)
      recordingIntervalRef.current = null
    }
    const currentDuration = recordingDuration
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.onstop = async () => {
        const mime = mediaRecorderRef.current?.mimeType || 'audio/webm'
        const blob = new Blob(audioChunksRef.current, { type: mime })
        if (mediaStreamRef.current) {
          mediaStreamRef.current.getTracks().forEach((track) => track.stop())
          mediaStreamRef.current = null
        }
        setIsSendingVoice(true)
        try {
          if (sendVoiceNote) {
            await sendVoiceNote(blob, Math.max(1, currentDuration))
          }
          discardRecording()
        } catch (err) {
          console.error('Failed to send voice note:', err)
        } finally {
          setIsSendingVoice(false)
        }
      }
      mediaRecorderRef.current.stop()
    }
    setIsRecording(false)
  }

  // The dictionary loads lazily (separate chunk); until then only the curated typo map runs.
  useEffect(() => {
    let cancelled = false
    loadSpellingAssets()
      .then(() => !cancelled && setSpellReady(true))
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [])

  // Names and usernames are never "corrected".
  const protectedWords = useMemo(() => {
    const words = new Set()
    const add = (value) =>
      String(value || '')
        .toLowerCase()
        .split(/[^a-z]+/)
        .filter((w) => w.length >= 2)
        .forEach((w) => words.add(w))
    try {
      add(JSON.parse(localStorage.getItem('ar_user') || '{}').username)
    } catch {
      // no stored user
    }
    const conv = (conversations || []).find((c) => c && c.id === activeConversationId)
    if (conv) {
      add(conv.title)
      add(conv.other_user?.username)
      add(conv.other_user?.display_name)
    }
    return words
  }, [conversations, activeConversationId])

  const {
    analyzedDraft,
    corrections,
    correctedText,
    completions,
    tone,
    recommendations = [],
    recommendationCategory = null,
    recommendationQuery = null,
    ambiguity = null,
    isAnalyzing,
    error: aiError,
    analyzeDraft,
    clearSuggestions,
  } = useDraftAssistant(activeConversationId, {
    analysis: aiPrefs.ai_draft_analysis,
    recommendations: aiPrefs.draft_recommendations,
    protectedWords,
    spellReady,
  })

  const [dismissedRecKeys, setDismissedRecKeys] = useState(() => new Set())
  const [dismissedAmbiguities, setDismissedAmbiguities] = useState(() => new Set())
  const [selectedFile, setSelectedFile] = useState(null)
  const [filePreviewUrl, setFilePreviewUrl] = useState(null)
  const [attachmentError, setAttachmentError] = useState(null)
  const fileInputRef = useRef(null)

  const MAX_FILE_SIZE = 10 * 1024 * 1024 // 10 MB strict limit
  const ALLOWED_EXTS = ['.jpg', '.jpeg', '.png', '.webp', '.gif', '.pdf', '.txt', '.doc', '.docx', '.xls', '.xlsx']

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    setAttachmentError(null)

    if (file.size > MAX_FILE_SIZE) {
      setAttachmentError(`File "${file.name}" exceeds the 10 MB limit (${(file.size / (1024 * 1024)).toFixed(1)} MB).`)
      e.target.value = ''
      return
    }

    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ALLOWED_EXTS.includes(ext)) {
      setAttachmentError(`File type "${ext}" is not supported. Supported: images (JPEG, PNG, WebP, GIF) and documents (PDF, TXT, DOC, DOCX, XLS, XLSX).`)
      e.target.value = ''
      return
    }

    setSelectedFile(file)
    if (file.type && file.type.startsWith('image/')) {
      try {
        if (typeof window !== 'undefined' && window.URL && typeof window.URL.createObjectURL === 'function') {
          const url = window.URL.createObjectURL(file)
          setFilePreviewUrl(url)
        } else {
          setFilePreviewUrl(null)
        }
      } catch {
        setFilePreviewUrl(null)
      }
    } else {
      setFilePreviewUrl(null)
    }
  }

  const handleRemoveFile = useCallback(() => {
    if (filePreviewUrl) {
      try {
        if (typeof window !== 'undefined' && window.URL && typeof window.URL.revokeObjectURL === 'function') {
          window.URL.revokeObjectURL(filePreviewUrl)
        }
      } catch {}
    }
    setSelectedFile(null)
    setFilePreviewUrl(null)
    setAttachmentError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [filePreviewUrl])

  useEffect(() => {
    setDismissedRecKeys(new Set())
    setDismissedAmbiguities(new Set())
    setSelectedFile(null)
    setFilePreviewUrl(null)
    setAttachmentError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }, [activeConversationId])

  const resizeTextarea = () => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, 140)}px`
  }

  useImperativeHandle(ref, () => ({
    setText: (text) => {
      setContent(text)
      setCaret(text.length)
      textareaRef.current?.focus()
    },
    focus: () => {
      textareaRef.current?.focus()
    },
  }))

  useLayoutEffect(() => {
    const el = textareaRef.current
    if (el && pendingSelection.current !== null) {
      const pos = Math.min(pendingSelection.current, el.value.length)
      el.setSelectionRange(pos, pos)
      pendingSelection.current = null
    }
  }, [content])

  useEffect(resizeTextarea, [content])

  useEffect(() => {
    analyzeDraft(content)
  }, [content, analyzeDraft])

  // New analysis result: reset per-suggestion UI state.
  useEffect(() => {
    setDismissedKeys(new Set())
    setAcceptedDraft(null)
    setShowCorrectionPreview(false)
  }, [analyzedDraft, corrections])

  useEffect(() => {
    setContent('')
    setShowCorrectionPreview(false)
  }, [activeConversationId])

  const suggestionsMatchDraft =
    analyzedDraft !== null && (content === analyzedDraft || (acceptedDraft !== null && content === acceptedDraft))

  const visibleCorrections = useMemo(
    () =>
      suggestionsMatchDraft
        ? corrections.filter((c) => !dismissedKeys.has(correctionKey(c)) && content.includes(c.original))
        : [],
    [suggestionsMatchDraft, corrections, dismissedKeys, content]
  )
  const hasCorrections = visibleCorrections.length > 0

  // Autocomplete works on the text before the caret and never touches text after it.
  const caretPos = Math.min(caret, content.length)
  const beforeCaret = content.slice(0, caretPos)
  const { local: localSuggestions, ai: aiSuggestions } = useWritingSuggestions(
    activeConversationId,
    beforeCaret,
    { enabled: suggestEnabled && !disabled, aiEnabled: aiSuggestEnabled },
  )
  const analysisCompletions = useMemo(
    () =>
      suggestionsMatchDraft && caretPos === content.length && content.trim()
        ? completions.slice(0, 2).map((c, i) => ({ id: `draft-${i}-${c.text}`, kind: 'ai', text: c.text, from: 0 }))
        : [],
    [suggestionsMatchDraft, caretPos, content, completions],
  )
  const suggestions = useMemo(() => {
    if (!suggestEnabled || dismissedAt === beforeCaret || !beforeCaret.trim()) return []
    const seen = new Set()
    // Instant local results lead, but AI/contextual ones are guaranteed a slot once they arrive.
    return [...localSuggestions.slice(0, 2), ...aiSuggestions, ...localSuggestions.slice(2), ...analysisCompletions]
      .filter((s) => {
        const k = s.text.trim().toLowerCase()
        if (!k || seen.has(k) || s.text === beforeCaret.slice(s.from)) return false
        seen.add(k)
        return true
      })
      .slice(0, MAX_SUGGESTIONS)
  }, [suggestEnabled, dismissedAt, beforeCaret, localSuggestions, aiSuggestions, analysisCompletions])
  const hasSuggestions = suggestions.length > 0
  const suggestionSig = suggestions.map((s) => s.id).join('|')
  const activeIndex = nav.sig === suggestionSig ? nav.index : -1
  const untouchedResult = content === analyzedDraft && dismissedKeys.size === 0

  const visibleRecommendations = useMemo(() => {
    if (!content.trim() || !recommendations || recommendations.length === 0) return []
    return recommendations.filter((r) => !dismissedRecKeys.has(r.id))
  }, [content, recommendations, dismissedRecKeys])

  const handleContentChange = (e) => {
    const nextVal = e.target.value
    const caretPos = e.target.selectionEnd
    setCaret(caretPos ?? nextVal.length)

    if (autoCorrectEnabled && nextVal.length > content.length && caretPos !== null) {
      const typedChar = nextVal[caretPos - 1]
      // Trigger auto-correction on word boundaries (space or punctuation)
      if ([' ', '.', ',', '!', '?', '\n'].includes(typedChar)) {
        const textBeforeCaret = nextVal.slice(0, caretPos - 1)
        const match = textBeforeCaret.match(/([a-zA-Z0-9_-]+)$/)
        if (match) {
          const lastWord = match[1]
          const lowerWord = lastWord.toLowerCase()
          if (!undoneWords.current.has(lowerWord)) {
            const before = textBeforeCaret.slice(0, textBeforeCaret.length - lastWord.length)
            const prevMatch = before.match(/(\S+)\s*$/)
            const fix = getWordCorrection(lastWord, {
              prev: prevMatch ? prevMatch[1] : null,
              atSentenceStart: !prevMatch || /[.!?]["')\]]*$/.test(prevMatch[1]) || before.trim() === '',
              protectedWords,
            })
            if (fix && fix.corrected !== lastWord) {
              const wordStart = caretPos - 1 - lastWord.length
              const correctedVal =
                nextVal.slice(0, wordStart) + fix.corrected + nextVal.slice(wordStart + lastWord.length)
              const newCaretPos = wordStart + fix.corrected.length + 1
              setCaret(newCaretPos)

              lastAutoCorrected.current = {
                original: lastWord,
                corrected: fix.corrected,
                index: wordStart,
                atLength: correctedVal.length,
              }

              pendingSelection.current = newCaretPos
              setContent(correctedVal)
              return
            }
          }
        }
      }
    }

    lastAutoCorrected.current = null
    if (emptyWarning && nextVal.trim()) {
      setEmptyWarning(false)
    }
    setContent(nextVal)
  }

  const handleSubmit = async (e) => {
    e?.preventDefault()
    if (!content.trim() && !selectedFile) {
      setEmptyWarning(true)
      setTimeout(() => setEmptyWarning(false), 4000)
      return
    }
    setEmptyWarning(false)
    if (disabled || socketStatus !== 'connected') return

    const messageContent = content.trim()
    const fileToSend = selectedFile
    const currentReplyTo = replyTo

    try {
      if (fileToSend) {
        await onSend(messageContent, fileToSend, currentReplyTo)
      } else if (currentReplyTo) {
        await onSend(messageContent, null, currentReplyTo)
      } else {
        await onSend(messageContent)
      }
      setContent('')
      handleRemoveFile()
      clearSuggestions()
      setShowCorrectionPreview(false)
      setDismissedRecKeys(new Set())
      setDismissedAmbiguities(new Set())
      if (setReplyTo) setReplyTo(null)
    } catch (err) {
      console.error('Failed to send message:', err)
      // Draft and replyTo are preserved for retry
    }
  }

  const handleAcceptOne = useCallback(
    (c, replacement = c.corrected) => {
      const next = replaceFirst(content, c.original, replacement)
      setDismissedKeys((prev) => new Set(prev).add(correctionKey(c)))
      setAcceptedDraft(next)
      setContent(next)
      textareaRef.current?.focus()
    },
    [content]
  )

  const handleDismissOne = useCallback((c) => {
    setDismissedKeys((prev) => new Set(prev).add(correctionKey(c)))
  }, [])

  const handleAcceptAll = useCallback(() => {
    const next =
      untouchedResult && correctedText
        ? correctedText
        : visibleCorrections.reduce((text, c) => replaceFirst(text, c.original, c.corrected), content)
    setContent(next)
    clearSuggestions()
    setShowCorrectionPreview(false)
    textareaRef.current?.focus()
  }, [untouchedResult, correctedText, visibleCorrections, content, clearSuggestions])

  const handleDismissAll = useCallback(() => {
    setDismissedKeys((prev) => {
      const next = new Set(prev)
      corrections.forEach((c) => next.add(correctionKey(c)))
      return next
    })
    setShowCorrectionPreview(false)
  }, [corrections])

  // Inserts a suggestion at the caret. Only text before the caret from `s.from` is replaced; the rest is kept.
  const handleAcceptSuggestion = useCallback(
    (s) => {
      const next = content.slice(0, s.from) + s.text + content.slice(caretPos)
      const pos = s.from + s.text.length
      setContent(next)
      setCaret(pos)
      setDismissedAt(null)
      lastAutoCorrected.current = null
      const el = textareaRef.current
      el?.focus()
      pendingSelection.current = pos
    },
    [content, caretPos]
  )

  const dismissSuggestions = useCallback(() => setDismissedAt(beforeCaret), [beforeCaret])

  const toggleSuggest = useCallback(() => {
    setSuggestEnabled((prev) => {
      writeFlag('ar_suggest', !prev)
      return !prev
    })
  }, [])

  const syncCaret = (e) => setCaret(e.currentTarget.selectionStart ?? 0)

  const handleKeyDown = (e) => {
    // If Backspace is pressed right after auto-correction, undo it cleanly
    if (e.key === 'Backspace' && lastAutoCorrected.current) {
      const lac = lastAutoCorrected.current
      const el = e.currentTarget
      if (el.selectionStart === lac.index + lac.corrected.length + 1 && el.selectionStart === el.selectionEnd) {
        e.preventDefault()
        const restored =
          content.slice(0, lac.index) + lac.original + content.slice(lac.index + lac.corrected.length)
        undoneWords.current.add(lac.original.toLowerCase())
        lastAutoCorrected.current = null
        pendingSelection.current = lac.index + lac.original.length
        setContent(restored)
        return
      }
    }

    const noModifier = !e.shiftKey && !e.ctrlKey && !e.altKey && !e.metaKey
    const el = e.currentTarget
    // Suggestions only react to keys while the caret sits where they were computed.
    const suggestionsActive =
      hasSuggestions && el.selectionStart === el.selectionEnd && el.selectionStart === caretPos && !e.nativeEvent?.isComposing
    if (suggestionsActive && noModifier) {
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !content.includes('\n')) {
        e.preventDefault()
        const step = e.key === 'ArrowDown' ? 1 : -1
        const count = suggestions.length
        const index = activeIndex === -1 ? (step === 1 ? 0 : count - 1) : (activeIndex + step + count) % count
        setNav({ sig: suggestionSig, index })
        return
      }
      if (e.key === 'Tab') {
        e.preventDefault()
        handleAcceptSuggestion(suggestions[Math.max(activeIndex, 0)])
        return
      }
      // Enter only inserts after the user explicitly highlighted a suggestion; otherwise it sends as before.
      if (e.key === 'Enter' && activeIndex >= 0) {
        e.preventDefault()
        handleAcceptSuggestion(suggestions[activeIndex])
        return
      }
    }
    if (e.key === 'Escape' && (hasCorrections || hasSuggestions)) {
      e.preventDefault()
      if (hasSuggestions) dismissSuggestions()
      if (hasCorrections) clearSuggestions()
      setShowCorrectionPreview(false)
      return
    }
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent?.isComposing) {
      e.preventDefault()
      handleSubmit()
    }
  }

  const isDisconnected = socketStatus !== 'connected'
  const previewText =
    untouchedResult && correctedText
      ? correctedText
      : visibleCorrections.reduce((text, c) => replaceFirst(text, c.original, c.corrected), content)

  return (
    <div className="p-3 bg-white/90 dark:bg-neutral-900/90 border-t border-neutral-200/80 dark:border-neutral-800 backdrop-blur-md">
      {isDisconnected && (
        <div className="mb-2 px-3 py-1.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200/60 dark:border-amber-800/40 flex items-center justify-between text-xs text-amber-800 dark:text-amber-200">
          <div className="flex items-center gap-1.5">
            <WifiOff className="w-3.5 h-3.5" />
            <span>
              {socketStatus === 'connecting'
                ? 'Reconnecting to real-time server...'
                : 'Real-time connection offline. Retrying...'}
            </span>
          </div>
          <RefreshCw className="w-3 h-3 animate-spin" />
        </div>
      )}

      {emptyWarning && (
        <div
          role="alert"
          aria-live="polite"
          data-testid="empty-message-warning"
          className="mb-2 px-3 py-2 rounded-xl bg-amber-50/90 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800/60 flex items-center gap-2 text-xs text-amber-800 dark:text-amber-200 shadow-sm"
        >
          <AlertCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
          <span>Your message is empty. Add a message or a clarification before sending.</span>
        </div>
      )}

      {/* Pre-Send Ambiguity Alignment Warning */}
      {Boolean(ambiguity?.detected && content.trim() && !dismissedAmbiguities.has(content.trim().toLowerCase())) && (
        <div
          role="region"
          aria-label="Pre-send message alignment suggestion"
          data-testid="pre-send-ambiguity-panel"
          className="mb-2 px-3.5 py-2.5 rounded-xl bg-amber-50/95 dark:bg-amber-950/40 border border-amber-300/80 dark:border-amber-800/60 shadow-sm"
        >
          <div className="flex items-start justify-between gap-2 mb-1.5">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-900 dark:text-amber-200">
              <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0" />
              <span>This message may be unclear.</span>
            </div>
            <button
              type="button"
              onClick={() => {
                setDismissedAmbiguities((prev) => new Set(prev).add(content.trim().toLowerCase()))
              }}
              className="p-1 rounded-md text-amber-600/70 hover:text-amber-800 dark:hover:text-amber-200 transition-colors"
              title="Dismiss warning"
              aria-label="Dismiss ambiguity warning"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <p className="text-xs text-amber-950 dark:text-amber-100 mb-2 leading-relaxed" data-testid="ambiguity-details">
            {ambiguity.details || 'The recipient may not know which task is due or the exact deadline.'}
          </p>

          {Array.isArray(ambiguity.suggestedActions) && ambiguity.suggestedActions.length > 0 && (
            <div className="mb-2">
              <span className="text-[11px] font-medium text-amber-800 dark:text-amber-300 block mb-1">
                Suggested actions:
              </span>
              <ul className="space-y-1">
                {ambiguity.suggestedActions.map((action, idx) => (
                  <li key={idx} className="flex items-center gap-1.5 text-xs text-amber-900/90 dark:text-amber-200/90">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-500 shrink-0" />
                    <span>{action}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex items-center gap-2 pt-1.5 border-t border-amber-200/60 dark:border-amber-800/40 flex-wrap">
            {ambiguity.improvedDraft && (
              <button
                type="button"
                onClick={() => {
                  setContent(ambiguity.improvedDraft)
                  textareaRef.current?.focus()
                }}
                className="px-2.5 py-1 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-medium flex items-center gap-1 transition-colors"
                data-testid="improve-message-btn"
              >
                <Sparkles className="w-3 h-3" />
                <span>Improve message</span>
              </button>
            )}
            <button
              type="button"
              onClick={async () => {
                const messageContent = content.trim()
                const fileToSend = selectedFile
                const currentReplyTo = replyTo
                try {
                  if (fileToSend) {
                    await onSend(messageContent, fileToSend, currentReplyTo)
                  } else if (currentReplyTo) {
                    await onSend(messageContent, null, currentReplyTo)
                  } else {
                    await onSend(messageContent)
                  }
                  setContent('')
                  handleRemoveFile()
                  clearSuggestions()
                  setShowCorrectionPreview(false)
                  setDismissedAmbiguities(new Set())
                  if (setReplyTo) setReplyTo(null)
                } catch (err) {
                  console.error('Failed to send message:', err)
                }
              }}
              className="px-2.5 py-1 rounded-lg bg-amber-100 dark:bg-amber-900/50 hover:bg-amber-200 dark:hover:bg-amber-900/80 text-amber-900 dark:text-amber-200 text-xs font-medium transition-colors"
              data-testid="send-anyway-btn"
            >
              Send anyway
            </button>
            <button
              type="button"
              onClick={() => {
                setDismissedAmbiguities((prev) => new Set(prev).add(content.trim().toLowerCase()))
              }}
              className="text-xs text-amber-700 dark:text-amber-400 hover:underline ml-auto"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Attachment Error Banner */}
      {attachmentError && (
        <div
          role="alert"
          data-testid="attachment-error-banner"
          className="mb-2 px-3 py-2 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs text-red-700 dark:text-red-300 flex items-center justify-between"
        >
          <span>{attachmentError}</span>
          <button type="button" onClick={() => setAttachmentError(null)} className="p-0.5 text-red-500 hover:text-red-700">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Attachment Staged Preview Dock */}
      {selectedFile && (
        <div
          role="region"
          aria-label="Attached file preview"
          data-testid="attachment-preview-dock"
          className="mb-2 p-2 rounded-xl bg-neutral-100 dark:bg-neutral-800/80 border border-neutral-200 dark:border-neutral-700 flex items-center gap-2.5"
        >
          {filePreviewUrl ? (
            <img
              src={filePreviewUrl}
              alt={selectedFile.name}
              className="w-12 h-12 rounded-lg object-cover border border-neutral-300 dark:border-neutral-600 shrink-0"
            />
          ) : (
            <div className="w-12 h-12 rounded-lg bg-neutral-200 dark:bg-neutral-700 flex items-center justify-center shrink-0">
              <FileText className="w-6 h-6 text-neutral-500 dark:text-neutral-400" />
            </div>
          )}
          <div className="min-w-0 flex-1 text-xs">
            <p className="font-medium text-neutral-900 dark:text-neutral-100 truncate" data-testid="attachment-name">{selectedFile.name}</p>
            <p className="text-neutral-500 dark:text-neutral-400 text-[11px]" data-testid="attachment-size">
              {selectedFile.size / 1024 < 1024
                ? `${(selectedFile.size / 1024).toFixed(1)} KB`
                : `${(selectedFile.size / (1024 * 1024)).toFixed(1)} MB`}
            </p>
          </div>
          <button
            type="button"
            onClick={handleRemoveFile}
            className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-200/60 dark:hover:bg-neutral-700/60 transition-colors"
            title="Remove attachment"
            aria-label="Remove attachment"
            data-testid="remove-attachment-btn"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {hasCorrections && (
        <div
          role="region"
          aria-label="Writing suggestions"
          data-testid="correction-panel"
          className="mb-2 px-3 py-2 rounded-xl bg-blue-50 dark:bg-blue-950/30 border border-blue-200/60 dark:border-blue-800/40"
        >
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="text-[11px] font-semibold text-blue-800 dark:text-blue-200 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-blue-500" />
              {visibleCorrections.length === 1 ? '1 writing suggestion' : `${visibleCorrections.length} writing suggestions`}
              {tone && (
                <span className="px-1.5 py-0.5 rounded-full bg-blue-100 dark:bg-blue-900/50 text-[10px] text-blue-600 dark:text-blue-300 font-medium">
                  {tone}
                </span>
              )}
            </span>
            <div className="flex items-center gap-2 shrink-0">
              <button
                type="button"
                onClick={() => setShowCorrectionPreview((v) => !v)}
                className="text-[11px] text-blue-600 dark:text-blue-400 font-medium hover:underline"
              >
                {showCorrectionPreview ? 'Hide preview' : 'Preview'}
              </button>
              <button
                type="button"
                onClick={handleAcceptAll}
                className="text-[11px] font-semibold px-2 py-0.5 rounded-md bg-blue-500 text-white hover:bg-blue-600"
              >
                Accept all
              </button>
              <button
                type="button"
                onClick={handleDismissAll}
                className="p-0.5 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                title="Dismiss all"
                aria-label="Dismiss all suggestions"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <ul className="space-y-1">
            {visibleCorrections.map((c) => (
              <li key={correctionKey(c)} className="flex items-center gap-1.5 text-xs flex-wrap">
                <span className="line-through text-red-500/80">{c.original}</span>
                <ChevronRight className="w-3 h-3 text-neutral-400" />
                <span className="text-emerald-700 dark:text-emerald-400 font-medium">{c.corrected}</span>
                {c.reason && <span className="text-[11px] text-neutral-500 truncate max-w-[16rem]">— {c.reason}</span>}
                {c.tier === 'suggest' &&
                  (c.alternatives || [])
                    .filter((alt) => alt !== c.corrected)
                    .slice(0, 2)
                    .map((alt) => (
                      <button
                        key={alt}
                        type="button"
                        onClick={() => handleAcceptOne(c, alt)}
                        className="px-1.5 py-0.5 rounded-md border border-neutral-200 dark:border-neutral-600 text-[11px] text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-700"
                        aria-label={`Use ${alt} instead of ${c.original}`}
                      >
                        {alt}
                      </button>
                    ))}
                <span className="ml-auto flex items-center gap-0.5">
                  <button
                    type="button"
                    onClick={() => handleAcceptOne(c)}
                    className="p-1 rounded-md text-emerald-600 hover:bg-emerald-100 dark:hover:bg-emerald-900/40"
                    title="Accept correction"
                    aria-label={`Accept correction ${c.original} to ${c.corrected}`}
                  >
                    <Check className="w-3.5 h-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => handleDismissOne(c)}
                    className="p-1 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
                    title="Dismiss"
                    aria-label={`Dismiss correction ${c.original}`}
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </span>
              </li>
            ))}
          </ul>

          {showCorrectionPreview && (
            <div className="mt-2 pt-2 border-t border-blue-200/60 dark:border-blue-800/40 text-xs space-y-1" data-testid="correction-preview">
              <p className="text-neutral-500"><span className="font-medium">Before:</span> {content}</p>
              <p className="text-neutral-800 dark:text-neutral-100"><span className="font-medium">After:</span> {previewText}</p>
            </div>
          )}
        </div>
      )}

      {/* Contextual Draft Recommendations Dock */}
      {visibleRecommendations.length > 0 && (
        <div
          className="mb-2.5 p-3 rounded-2xl bg-white/95 dark:bg-neutral-850/95 border border-neutral-200/90 dark:border-neutral-700/80 shadow-subtle backdrop-blur-sm transition-all"
          role="region"
          aria-label="Contextual draft recommendations"
          data-testid="draft-recommendations-dock"
        >
          <div className="flex items-center justify-between gap-2 mb-2 px-1">
            <span className="text-[11px] font-semibold text-neutral-800 dark:text-neutral-200 flex items-center gap-1.5">
              {recommendationCategory === 'music' ? (
                <Music className="w-3.5 h-3.5 text-emerald-500" />
              ) : recommendationCategory === 'movie' ? (
                <Video className="w-3.5 h-3.5 text-rose-500" />
              ) : (
                <Sparkles className="w-3.5 h-3.5 text-blue-500" />
              )}
              <span>Contextual Suggestions</span>
              {recommendationQuery && (
                <span className="px-1.5 py-0.5 rounded-full bg-neutral-100 dark:bg-neutral-750 text-[10px] text-neutral-600 dark:text-neutral-300 font-medium">
                  "{recommendationQuery}"
                </span>
              )}
            </span>
            <button
              type="button"
              onClick={() => {
                setDismissedRecKeys((prev) => {
                  const next = new Set(prev)
                  visibleRecommendations.forEach((r) => next.add(r.id))
                  return next
                })
              }}
              className="p-1 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 transition-colors"
              title="Dismiss suggestions"
              aria-label="Dismiss draft recommendations"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>

          <div className="flex flex-col sm:flex-row gap-2.5 overflow-x-auto pb-1">
            {visibleRecommendations.slice(0, 3).map((rec) => (
              <div key={rec.id} className="flex-1 min-w-[260px]">
                <RecommendationCard recommendation={rec} compact={true} />
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Quoted Reply Preview Banner */}
      {replyTo && (
        <div
          role="region"
          aria-label="Replying to message preview"
          data-testid="composer-reply-preview"
          className="mb-2 px-3.5 py-2 rounded-xl bg-neutral-100 dark:bg-neutral-800 border-l-4 border-apple-blue dark:border-blue-400 text-xs text-neutral-800 dark:text-neutral-200 flex items-center justify-between gap-3 shadow-subtle animate-in fade-in slide-in-from-bottom-1 duration-150"
        >
          <div className="flex items-center gap-2.5 min-w-0">
            <Reply className="w-4 h-4 text-apple-blue dark:text-blue-400 shrink-0" />
            <div className="truncate">
              <span className="font-semibold text-apple-blue dark:text-blue-400 block truncate">
                Replying to @{replyTo.sender_username || 'User'}
              </span>
              <span className="text-[11px] text-neutral-500 dark:text-neutral-400 truncate block">
                {replyTo.is_deleted_for_everyone
                  ? 'This message was deleted.'
                  : replyTo.content || (replyTo.has_attachment || (replyTo.attachments && replyTo.attachments.length > 0) ? 'Attachment' : 'Message')}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setReplyTo && setReplyTo(null)}
            className="p-1 rounded-full text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors shrink-0"
            title="Cancel reply"
            aria-label="Cancel reply"
            data-testid="cancel-reply-btn"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      <input
        ref={fileInputRef}
        type="file"
        onChange={handleFileSelect}
        className="hidden"
        accept=".jpg,.jpeg,.png,.webp,.gif,.pdf,.txt,.doc,.docx,.xls,.xlsx"
        data-testid="file-upload-input"
      />

      {/* Microphone permission or device error */}
      {micPermissionError && (
        <div
          className="mb-2 px-3 py-1.5 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-xs text-amber-800 dark:text-amber-200 flex items-center justify-between gap-2 shadow-subtle animate-in fade-in duration-150"
          data-testid="mic-permission-error"
        >
          <div className="flex items-center gap-1.5 min-w-0">
            <AlertCircle className="w-3.5 h-3.5 text-amber-500 shrink-0" />
            <span className="truncate">{micPermissionError}</span>
          </div>
          <button
            type="button"
            onClick={() => setMicPermissionError(null)}
            className="p-1 rounded-full text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 shrink-0"
            title="Dismiss error"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}

      {/* Active Recording Dock */}
      {isRecording ? (
        <div
          className="flex items-center justify-between gap-3 bg-neutral-100 dark:bg-neutral-800/90 rounded-2xl p-2.5 border border-neutral-200/60 dark:border-neutral-700/60 shadow-sm animate-in fade-in duration-150"
          data-testid="voice-recording-dock"
        >
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 animate-ping shrink-0" />
            <span className="text-xs font-mono font-medium text-neutral-700 dark:text-neutral-200">
              {formatSeconds(recordingDuration)}
            </span>
            {/* Visual recording waveform activity */}
            <div className="flex items-center gap-0.5 h-4 ml-1">
              <span className="w-1 bg-red-400 rounded-full animate-bounce h-2" style={{ animationDelay: '0ms' }} />
              <span className="w-1 bg-red-400 rounded-full animate-bounce h-3.5" style={{ animationDelay: '150ms' }} />
              <span className="w-1 bg-red-400 rounded-full animate-bounce h-4" style={{ animationDelay: '300ms' }} />
              <span className="w-1 bg-red-400 rounded-full animate-bounce h-2.5" style={{ animationDelay: '200ms' }} />
              <span className="w-1 bg-red-400 rounded-full animate-bounce h-3" style={{ animationDelay: '100ms' }} />
            </div>
          </div>

          <div className="flex items-center gap-1.5 sm:gap-2">
            <button
              type="button"
              onClick={discardRecording}
              className="p-1.5 rounded-full text-neutral-500 hover:text-red-600 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
              title="Discard recording"
              aria-label="Discard recording"
              data-testid="discard-recording-btn"
            >
              <Trash2 className="w-4 h-4" />
            </button>

            <button
              type="button"
              onClick={stopRecording}
              className="px-2.5 py-1 rounded-xl bg-neutral-200 dark:bg-neutral-700 text-neutral-700 dark:text-neutral-200 hover:bg-neutral-300 dark:hover:bg-neutral-600 text-xs font-medium flex items-center gap-1 transition-colors"
              title="Stop and review recording"
              data-testid="stop-review-recording-btn"
            >
              <Square className="w-3 h-3 fill-current" />
              <span>Review</span>
            </button>

            <button
              type="button"
              onClick={stopRecordingAndSend}
              disabled={isSendingVoice}
              className="p-1.5 rounded-full bg-apple-blue hover:bg-blue-600 text-white shadow-sm flex items-center justify-center transition-transform active:scale-95 disabled:opacity-50"
              title="Send voice note directly"
              aria-label="Send voice note"
              data-testid="send-recorded-voice-btn"
            >
              {isSendingVoice ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <ArrowUp className="w-4 h-4" />
              )}
            </button>
          </div>
        </div>
      ) : audioBlob ? (
        /* Review / Preview Recorded Voice Note Dock */
        <div
          className="flex items-center justify-between gap-3 bg-neutral-100 dark:bg-neutral-800 rounded-2xl p-2.5 border border-neutral-200 dark:border-neutral-700 shadow-sm animate-in fade-in duration-150"
          data-testid="voice-preview-dock"
        >
          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={togglePreviewPlay}
              className="w-8 h-8 rounded-full bg-apple-blue text-white flex items-center justify-center shadow-sm shrink-0"
              title={isPlayingPreview ? 'Pause preview' : 'Play preview'}
              aria-label={isPlayingPreview ? 'Pause preview' : 'Play preview'}
              data-testid="preview-play-btn"
            >
              {isPlayingPreview ? (
                <Pause className="w-3.5 h-3.5 fill-current" />
              ) : (
                <Play className="w-3.5 h-3.5 ml-0.5 fill-current" />
              )}
            </button>
            <div className="text-xs text-neutral-700 dark:text-neutral-200 font-mono">
              <span>Voice Note ({formatSeconds(recordingDuration)})</span>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={discardRecording}
              className="p-1.5 rounded-full text-neutral-500 hover:text-red-600 hover:bg-neutral-200 dark:hover:bg-neutral-700 transition-colors"
              title="Delete voice note"
              aria-label="Delete recording"
              data-testid="discard-preview-btn"
            >
              <Trash2 className="w-4 h-4" />
            </button>

            <Button
              type="button"
              onClick={handleSendVoiceNote}
              disabled={isSendingVoice}
              variant="primary"
              size="sm"
              className="rounded-xl flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold"
              data-testid="confirm-send-voice-btn"
            >
              {isSendingVoice ? (
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <ArrowUp className="w-3.5 h-3.5" />
              )}
              <span>Send</span>
            </Button>
          </div>
        </div>
      ) : (
        /* Normal text & media composer form */
        <form
          onSubmit={handleSubmit}
          className="flex items-end gap-1.5 sm:gap-2 bg-neutral-100 dark:bg-neutral-800/90 rounded-2xl p-1.5 border border-neutral-200/60 dark:border-neutral-700/60 focus-within:border-apple-blue focus-within:ring-2 focus-within:ring-apple-blue/20 transition-all"
        >
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || isDisconnected}
            className="p-1.5 rounded-full text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-200/50 dark:hover:bg-neutral-700/50 transition-colors shrink-0 mb-0.5"
            title="Attach image or document (up to 10 MB)"
            aria-label="Attach file"
            data-testid="attach-file-btn"
          >
            <Paperclip className="w-4 h-4" />
          </button>

          <button
            type="button"
            onClick={startRecording}
            disabled={disabled || isDisconnected}
            className="p-1.5 rounded-full text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 hover:bg-neutral-200/50 dark:hover:bg-neutral-700/50 transition-colors shrink-0 mb-0.5"
            title="Record voice message"
            aria-label="Record voice message"
            data-testid="composer-mic-btn"
          >
            <Mic className="w-4 h-4" />
          </button>

          <textarea
            ref={textareaRef}
            rows={1}
            value={content}
            onChange={handleContentChange}
            onKeyDown={handleKeyDown}
            onSelect={syncCaret}
            onClick={syncCaret}
            onKeyUp={syncCaret}
            role="combobox"
            aria-label="Message"
            aria-autocomplete="list"
            aria-expanded={hasSuggestions}
            aria-controls="composer-suggestions"
            aria-activedescendant={hasSuggestions && activeIndex >= 0 ? `composer-suggestion-${activeIndex}` : undefined}
            placeholder="Message or ask for alignment..."
            disabled={disabled}
            className="flex-1 bg-transparent px-2 sm:px-3 py-1.5 text-sm text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 focus:outline-none resize-none max-h-36 leading-relaxed"
          />

          {isAnalyzing && (
            <div className="shrink-0 flex items-center justify-center w-8 h-8" aria-label="Checking writing">
              <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
            </div>
          )}

          <Button
            type="submit"
            variant="primary"
            size="icon"
            disabled={(!content.trim() && !selectedFile) || disabled || isDisconnected}
            className="w-8 h-8 rounded-full shrink-0 flex items-center justify-center p-0 transition-transform"
            aria-label="Send message"
          >
            <ArrowUp className="w-4 h-4" />
          </Button>
        </form>
      )}

      <div className="sr-only" role="status" aria-live="polite">
        {hasSuggestions ? `${suggestions.length} suggestions available. Use arrow keys to browse, Tab to insert, Escape to dismiss.` : ''}
      </div>
      {hasSuggestions && (
        <div
          data-testid="autocomplete-panel"
          className="mt-1.5 rounded-xl bg-white dark:bg-neutral-800 border border-neutral-200/80 dark:border-neutral-700/70 shadow-sm overflow-hidden"
        >
          <ul id="composer-suggestions" role="listbox" aria-label="Autocomplete suggestions">
            {suggestions.map((s, i) => (
              <li
                key={s.id}
                id={`composer-suggestion-${i}`}
                role="option"
                aria-selected={i === activeIndex}
                // Keep focus (and the caret) in the textarea while pointing at an option.
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => handleAcceptSuggestion(s)}
                className={`min-h-[40px] sm:min-h-[32px] px-3 py-2 sm:py-1.5 flex items-center gap-2 text-sm sm:text-xs cursor-pointer text-neutral-700 dark:text-neutral-200 ${
                  i === activeIndex ? 'bg-blue-50 dark:bg-blue-950/40' : 'hover:bg-neutral-50 dark:hover:bg-neutral-700/50'
                }`}
              >
                <ChevronRight className="w-3 h-3 text-neutral-400 shrink-0" aria-hidden="true" />
                <span className="truncate min-w-0 flex-1" data-testid="suggestion-text">{s.text}</span>
                {s.kind === 'ai' && <span className="text-[10px] text-blue-500 shrink-0">AI</span>}
                {i === 0 && activeIndex < 1 && <kbd className="hidden sm:inline text-[10px] text-neutral-400 shrink-0">Tab</kbd>}
              </li>
            ))}
          </ul>
          <button
            type="button"
            onClick={dismissSuggestions}
            className="w-full flex items-center justify-end gap-1 px-3 py-1 text-[10px] text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300 border-t border-neutral-100 dark:border-neutral-700/50"
            aria-label="Dismiss autocomplete suggestions"
          >
            <X className="w-3 h-3" aria-hidden="true" />
            <span>Dismiss</span>
          </button>
        </div>
      )}

      {showPrivacy && (
        <div
          id="draft-ai-privacy"
          role="group"
          aria-label="Draft AI privacy settings"
          data-testid="draft-ai-privacy"
          className="mt-1.5 p-3 rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800 text-xs text-neutral-700 dark:text-neutral-200 space-y-2"
        >
          <p className="text-[11px] text-neutral-500">
            By default your unsent text stays on this device and is only checked locally. Turn on a feature below to let
            the server send your draft to an external service. Sent messages are analysed separately for alignment.
          </p>
          {[
            ['ai_draft_analysis', 'AI writing check', 'Sends your draft and recent messages from this chat to an AI provider (Groq or NVIDIA) for contextual corrections.'],
            ['ai_autocomplete', 'AI completions', 'Sends what you type and the last few messages of this chat to an AI provider (Groq) to suggest completions.'],
            ['draft_recommendations', 'Draft recommendations', 'Sends a search query derived from your draft to Spotify, YouTube or Tavily to suggest links.'],
          ].map(([key, label, detail]) => (
            <label key={key} className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={aiPrefs[key]}
                onChange={(e) => setPref(key, e.target.checked)}
              />
              <span>
                <span className="font-medium">{label}</span>
                <span className="block text-[11px] text-neutral-500">{detail}</span>
              </span>
            </label>
          ))}
          {prefsError && <p role="alert" className="text-[11px] text-amber-600">{prefsError}</p>}
        </div>
      )}
      <div className="flex flex-wrap justify-between items-center gap-y-1 px-1 mt-1 text-[10px] text-neutral-400 select-none">
        <span>Press Enter to send, Shift+Enter for new line{hasSuggestions ? ', Tab to complete' : ''}</span>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <button
            type="button"
            onClick={toggleSuggest}
            aria-pressed={suggestEnabled}
            className={`text-[10px] font-medium transition-colors ${suggestEnabled ? 'text-apple-blue dark:text-blue-400 hover:underline' : 'text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300'}`}
            title="Show word and phrase suggestions while typing"
          >
            Suggestions {suggestEnabled ? 'On' : 'Off'}
          </button>
          <button
            type="button"
            onClick={() => setShowPrivacy((v) => !v)}
            aria-expanded={showPrivacy}
            aria-controls="draft-ai-privacy"
            className="text-[10px] font-medium text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300 hover:underline"
          >
            Draft AI privacy
          </button>
          <button
            type="button"
            onClick={toggleAutoCorrect}
            className={`flex items-center gap-1 text-[10px] font-medium transition-colors ${
              autoCorrectEnabled
                ? 'text-apple-blue dark:text-blue-400 hover:underline'
                : 'text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300'
            }`}
            title="Toggle automatic typo correction while typing"
            aria-label={`Toggle auto-correction. Currently ${autoCorrectEnabled ? 'enabled' : 'disabled'}`}
          >
            <Wand2 className="w-3 h-3" />
            <span>Auto-correct {autoCorrectEnabled ? 'On' : 'Off'}</span>
          </button>
          <span className="flex items-center gap-1" aria-live="polite">
            {isAnalyzing ? 'Checking writing…' : aiError ? <span className="text-amber-500">{aiError}</span> : aiPrefs.ai_draft_analysis ? 'Writing assistant on' : 'Local checks only — AI writing check is off (see Draft AI privacy)'}
          </span>
        </div>
      </div>
    </div>
  )
})
