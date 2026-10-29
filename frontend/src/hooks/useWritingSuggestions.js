import { useState, useEffect, useRef, useMemo } from 'react'
import { aiService } from '../services/aiService'
import { getLocalSuggestions } from '../utils/autocomplete'

export const AI_DEBOUNCE_MS = 450
export const AI_MIN_CHARS = 5
const AI_MAX_CHARS = 600
const CACHE_LIMIT = 40

export const isAiEligible = (draft) => {
  const t = draft.trim()
  return t.length >= AI_MIN_CHARS && draft.length <= AI_MAX_CHARS && !/[.!?]$/.test(t)
}

/**
 * Autocomplete for the text before the caret.
 * - local suggestions are computed synchronously on every change (no network);
 * - AI suggestions (opt-in only) are fetched after a debounce, aborted when the user keeps typing,
 *   cached per conversation + text, and only ever shown for the exact text they were produced for.
 */
export function useWritingSuggestions(conversationId, textBeforeCaret, { enabled = true, aiEnabled = false } = {}) {
  const [aiResults, setAiResults] = useState({})
  const cacheRef = useRef(new Map())
  const revisionRef = useRef(0)

  const local = useMemo(
    () => (enabled ? getLocalSuggestions(textBeforeCaret) : []),
    [enabled, textBeforeCaret],
  )

  const key = `${conversationId}\u0000${textBeforeCaret}`

  useEffect(() => {
    if (!enabled || !aiEnabled || !conversationId || !isAiEligible(textBeforeCaret)) return undefined

    const cached = cacheRef.current.has(key)
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      if (cached) {
        const hit = cacheRef.current.get(key)
        setAiResults((prev) => ({ ...prev, [key]: hit }))
        return
      }
      const revision = ++revisionRef.current
      try {
        const data = await aiService.suggestDraft(conversationId, textBeforeCaret, `sug-${revision}`, controller.signal)
        if (controller.signal.aborted || !data || data.draft_revision !== `sug-${revision}`) return
        const items = (Array.isArray(data.suggestions) ? data.suggestions : [])
          .map((s) => s?.text)
          .filter((t) => typeof t === 'string' && t.trim())
          .map((t, i) => ({ id: `ai-${i}-${t.toLowerCase()}`, kind: 'ai', text: t, from: 0 }))
        cacheRef.current.set(key, items)
        if (cacheRef.current.size > CACHE_LIMIT) cacheRef.current.delete(cacheRef.current.keys().next().value)
        setAiResults((prev) => {
          const keys = Object.keys(prev)
          const base = keys.length >= CACHE_LIMIT ? {} : prev
          return { ...base, [key]: items }
        })
      } catch {
        // Provider failure or timeout: local suggestions remain the fallback.
      }
    }, cached ? 0 : AI_DEBOUNCE_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [enabled, aiEnabled, conversationId, textBeforeCaret, key])

  const ai = enabled && aiEnabled ? aiResults[key] || [] : []
  return { local, ai }
}
