import { useState, useRef, useCallback, useEffect } from 'react'
import { aiService } from '../services/aiService'
import { analyzeDraftLocally } from '../utils/spellingEngine'
import { detectDraftAmbiguityLocally } from '../utils/ambiguityEngine'

export const DEBOUNCE_MS = 400
export const MIN_DRAFT_LENGTH = 4

const EMPTY = {
  analyzedDraft: null,
  corrections: [],
  correctedText: null,
  completions: [],
  tone: null,
  recommendations: [],
  recommendationCategory: null,
  recommendationQuery: null,
  ambiguity: null,
}

/**
 * Debounced writing assistance and contextual recommendations for the composer.
 * Combines instant local dictionary suggestions, contextual NVIDIA inference,
 * and proactive Spotify / YouTube draft recommendations while typing.
 */
export function useDraftAssistant(
  conversationId,
  { analysis = false, recommendations: remoteRecs = false, protectedWords = undefined, spellReady = false } = {},
) {
  const [result, setResult] = useState(EMPTY)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [error, setError] = useState(null)

  const debounceTimer = useRef(null)
  const latestRevision = useRef(0)
  const abortRef = useRef(null)
  // Identical drafts are never sent twice (callback identity changes when the dictionary or names load).
  const responseCache = useRef(new Map())

  const cancelPending = useCallback(() => {
    if (debounceTimer.current) clearTimeout(debounceTimer.current)
    debounceTimer.current = null
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = null
    // Invalidate any response still in flight.
    latestRevision.current += 1
  }, [])

  const clearSuggestions = useCallback(() => {
    cancelPending()
    setResult(EMPTY)
    setIsAnalyzing(false)
    setError(null)
  }, [cancelPending])

  useEffect(() => {
    clearSuggestions()
  }, [conversationId, clearSuggestions])

  const analyzeDraft = useCallback(
    (draft) => {
      cancelPending()

      if (!draft || draft.trim().length < MIN_DRAFT_LENGTH || !conversationId) {
        setResult(EMPTY)
        setIsAnalyzing(false)
        return
      }

      debounceTimer.current = setTimeout(async () => {
        debounceTimer.current = null
        const revisionNumber = latestRevision.current + 1
        latestRevision.current = revisionNumber
        const revision = `rev-${revisionNumber}`
        const controller = new AbortController()
        abortRef.current = controller

        // 1. Instant local typo and ambiguity detection for this draft
        const local = analyzeDraftLocally(draft, { protectedWords })
        const localAmbiguity = detectDraftAmbiguityLocally(draft)
        if (local.corrections.length > 0 || localAmbiguity) {
          setResult((prev) => ({
            ...prev,
            analyzedDraft: draft,
            corrections: local.corrections,
            correctedText: local.correctedText,
            completions: [],
            tone: null,
            ambiguity: localAmbiguity ? {
              detected: true,
              details: localAmbiguity.ambiguityDetails,
              suggestedActions: localAmbiguity.suggestedActions,
              clarificationPrompt: localAmbiguity.clarificationPrompt,
              improvedDraft: localAmbiguity.improvedDraft,
            } : null,
          }))
        }

        setIsAnalyzing(true)

        try {
          // External services are only contacted for the parts the user explicitly opted into.
          const cacheKeyEarly = `${conversationId} ${analysis ? 1 : 0}${remoteRecs ? 1 : 0} ${draft.trim()}`
          const hit = responseCache.current.has(cacheKeyEarly)
          const recsPromise = !hit && remoteRecs && typeof aiService.getDraftRecommendations === 'function'
            ? aiService.getDraftRecommendations(conversationId, draft, revision, controller.signal).catch(() => null)
            : Promise.resolve(null)

          const analyzePromise = (analysis && !hit
            ? aiService.analyzeDraft(conversationId, draft, revision, controller.signal)
            : Promise.resolve(null)
          ).catch((err) => {
            if (err?.name !== 'CanceledError' && err?.code !== 'ERR_CANCELED') {
              console.warn('Draft analysis warning:', err)
            }
            return null
          })

          const cacheKey = `${conversationId} ${analysis ? 1 : 0}${remoteRecs ? 1 : 0} ${draft.trim()}`
          const cached = responseCache.current.get(cacheKey)
          const [data, recData] = cached || (await Promise.all([analyzePromise, recsPromise]))
          if (revisionNumber !== latestRevision.current) return
          if (!cached && (data || recData)) {
            responseCache.current.set(cacheKey, [data, recData])
            if (responseCache.current.size > 30) responseCache.current.delete(responseCache.current.keys().next().value)
          }

          const aiCorrections = (data && Array.isArray(data.corrections)) ? data.corrections : []
          const seenOriginals = new Set(aiCorrections.map((c) => c.original?.toLowerCase()))
          const mergedCorrections = [...aiCorrections]

          for (const lc of local.corrections) {
            if (!seenOriginals.has(lc.original.toLowerCase())) {
              mergedCorrections.push(lc)
              seenOriginals.add(lc.original.toLowerCase())
            }
          }

          let finalCorrectedText = data?.corrected_text || null
          if (!finalCorrectedText && mergedCorrections.length > 0) {
            finalCorrectedText = local.correctedText
          }

          const recs = (recData?.recommendations && recData.recommendations.length > 0)
            ? recData.recommendations
            : (Array.isArray(data?.recommendations) ? data.recommendations : [])

          if (analysis && (!data || data?.ai_available === false) && !data?.ai_consent_required && local.corrections.length === 0 && recs.length === 0 && !localAmbiguity) {
            setResult(EMPTY)
            setError('Writing assistant unavailable')
            return
          }
          setError(null)

          const ambiguityResult = data?.ambiguity_detected ? {
            detected: true,
            details: data.ambiguity_details,
            suggestedActions: data.suggested_actions || [],
            clarificationPrompt: data.clarification_prompt,
            improvedDraft: data.improved_draft,
          } : (localAmbiguity ? {
            detected: true,
            details: localAmbiguity.ambiguityDetails,
            suggestedActions: localAmbiguity.suggestedActions,
            clarificationPrompt: localAmbiguity.clarificationPrompt,
            improvedDraft: localAmbiguity.improvedDraft,
          } : null)

          setResult({
            analyzedDraft: draft,
            corrections: mergedCorrections,
            correctedText: finalCorrectedText,
            completions: Array.isArray(data?.completions) ? data.completions.slice(0, 2) : [],
            tone: data?.tone || null,
            recommendations: recs,
            recommendationCategory: recData?.category || (recs.length > 0 ? recs[0].category : null),
            recommendationQuery: recData?.query || null,
            ambiguity: ambiguityResult,
          })
        } catch (err) {
          if (revisionNumber !== latestRevision.current) return
          if (err?.name !== 'CanceledError' && err?.code !== 'ERR_CANCELED') {
            if (local.corrections.length === 0 && !localAmbiguity) {
              setResult(EMPTY)
            } else if (localAmbiguity) {
              setResult((prev) => ({
                ...prev,
                analyzedDraft: draft,
                ambiguity: {
                  detected: true,
                  details: localAmbiguity.ambiguityDetails,
                  suggestedActions: localAmbiguity.suggestedActions,
                  clarificationPrompt: localAmbiguity.clarificationPrompt,
                  improvedDraft: localAmbiguity.improvedDraft,
                },
              }))
            }
            setError('Writing assistant unavailable')
          }
        } finally {
          if (revisionNumber === latestRevision.current) {
            setIsAnalyzing(false)
            abortRef.current = null
          }
        }
      }, DEBOUNCE_MS)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [conversationId, cancelPending, analysis, remoteRecs, protectedWords, spellReady]
  )

  useEffect(() => cancelPending, [cancelPending])

  return {
    ...result,
    isAnalyzing,
    error,
    analyzeDraft,
    clearSuggestions,
  }
}
