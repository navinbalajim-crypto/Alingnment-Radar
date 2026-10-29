import { useState, useEffect, useCallback, useRef } from 'react'
import { aiService } from '../services/aiService'

export const NO_CONSENT = Object.freeze({
  ai_draft_analysis: false,
  ai_autocomplete: false,
  draft_recommendations: false,
})

/**
 * Per-user consent for sending unsent drafts to external services. The backend is the source of truth and
 * enforces it; this hook mirrors it for the UI. Until the server answers (or if it fails) everything is OFF.
 */
export function useAiPreferences() {
  const [prefs, setPrefs] = useState(NO_CONSENT)
  const [loaded, setLoaded] = useState(false)
  const [error, setError] = useState(null)
  const version = useRef(0)

  useEffect(() => {
    let cancelled = false
    if (typeof aiService.getAiPreferences !== 'function') return undefined
    aiService
      .getAiPreferences()
      .then((data) => {
        if (!cancelled && data) setPrefs({ ...NO_CONSENT, ...data })
      })
      .catch(() => {})
      .finally(() => {
        if (!cancelled) setLoaded(true)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const setPref = useCallback((key, value) => {
    const previous = version.current
    version.current += 1
    // Revoking applies instantly; granting is only reflected after the server confirms it.
    if (!value) setPrefs((p) => ({ ...p, [key]: false }))
    setError(null)
    return aiService
      .updateAiPreferences({ [key]: value })
      .then((data) => {
        if (data) setPrefs({ ...NO_CONSENT, ...data })
      })
      .catch(() => {
        setError('Could not save your AI privacy setting.')
        if (value) setPrefs((p) => ({ ...p, [key]: false }))
        version.current = previous
      })
  }, [])

  return { prefs, loaded, error, setPref }
}
