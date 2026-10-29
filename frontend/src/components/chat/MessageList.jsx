import React, { useEffect, useRef } from 'react'
import { MessageBubble } from './MessageBubble'
import { AlignmentFindingCard } from '../ai/AlignmentFindingCard'
import { RecommendationCard } from '../ai/RecommendationCard'
import { ContextSuggestionCard } from '../ai/ContextSuggestionCard'
import { Button } from '../ui/Button'
import { MessageSquare, ArrowUp } from 'lucide-react'

export function MessageList({
  conversationId = null,
  messages = [],
  aiFindings = [],
  aiRecommendations = [],
  contextGraph = { active_nodes: [], inconsistencies: [] },
  onDismissInconsistency,
  onResolveInconsistency,
  onHighlightEvidence,
  isLoading = false,
  hasMore = false,
  onLoadMore,
  onApplyQuestion,
}) {
  const bottomRef = useRef(null)
  const containerRef = useRef(null)
  // Identity of the previously-rendered message batch, so a conversation switch, an older
  // page being prepended, and a new message being appended can be told apart -- they all
  // change messages.length, but need completely different scroll handling.
  const prevRef = useRef({ conversationId: null, firstId: null, lastId: null, length: 0 })
  const isNearBottomRef = useRef(true)

  // Track whether the user is close to the bottom, so an incoming message only auto-scrolls
  // when they're already following the conversation -- not while they're reading upward.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return undefined
    const onScroll = () => {
      isNearBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
    }
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  useEffect(() => {
    const el = containerRef.current
    const prev = prevRef.current
    const firstId = messages[0] ? String(messages[0].id || messages[0].client_id) : null
    const lastId = messages.length ? String(messages[messages.length - 1].id || messages[messages.length - 1].client_id) : null

    if (conversationId !== prev.conversationId) {
      // A different conversation was just opened: always land on its newest message,
      // instantly (no animation), regardless of how many messages it has relative to the
      // previous conversation -- comparing lengths across a conversation switch is what
      // previously left the viewport wherever it happened to be.
      if (messages.length > 0) {
        requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'auto' }))
      }
      isNearBottomRef.current = true
    } else if (el && prev.length > 0 && messages.length > prev.length && firstId !== prev.firstId && lastId === prev.lastId) {
      // Older messages were prepended (pagination): keep whatever the user was looking at
      // in view by compensating for the new content's height, instead of jumping anywhere.
      const prevScrollHeight = el.scrollHeight
      requestAnimationFrame(() => {
        el.scrollTop += el.scrollHeight - prevScrollHeight
      })
    } else if (lastId !== prev.lastId && messages.length >= prev.length) {
      // A message was appended at the end (sent or received). Only follow it down if the
      // user was already at the bottom; otherwise leave their reading position alone.
      if (isNearBottomRef.current) {
        bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
      }
    }

    prevRef.current = { conversationId, firstId, lastId, length: messages.length }
  }, [conversationId, messages])

  if (isLoading && messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 space-y-3">
        <div className="w-8 h-8 rounded-full border-2 border-apple-blue border-t-transparent animate-spin" />
        <p className="text-xs text-neutral-400">Loading conversation history...</p>
      </div>
    )
  }

  if (!isLoading && messages.length === 0) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center p-8 text-center select-none">
        <div className="w-14 h-14 rounded-3xl bg-neutral-100 dark:bg-neutral-800 flex items-center justify-center text-neutral-400 mb-3 shadow-subtle">
          <MessageSquare className="w-7 h-7" />
        </div>
        <h3 className="text-sm font-semibold text-neutral-800 dark:text-neutral-200">
          No messages yet
        </h3>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 max-w-xs">
          Send a message to start aligning with your teammates. Alignment Radar will assist in real-time.
        </p>
      </div>
    )
  }

  // Map AI items by triggered_by_message_id for contextual inline placement
  const findingsByTrigger = new Map()
  const unassignedFindings = []
  aiFindings.forEach((f) => {
    const triggerId = f.triggered_by_message_id ? String(f.triggered_by_message_id) : null
    if (triggerId) {
      if (!findingsByTrigger.has(triggerId)) {
        findingsByTrigger.set(triggerId, [])
      }
      findingsByTrigger.get(triggerId).push(f)
    } else {
      unassignedFindings.push(f)
    }
  })

  const recsByTrigger = new Map()
  const unassignedRecs = []
  aiRecommendations.forEach((r) => {
    const triggerId = r.triggered_by_message_id ? String(r.triggered_by_message_id) : null
    if (triggerId) {
      if (!recsByTrigger.has(triggerId)) {
        recsByTrigger.set(triggerId, [])
      }
      recsByTrigger.get(triggerId).push(r)
    } else {
      unassignedRecs.push(r)
    }
  })

  // Map active context graph inconsistencies by triggering/evidence message
  const inconsistenciesByTrigger = new Map()
  const unassignedInconsistencies = []
  const inconsistencies = (contextGraph && contextGraph.inconsistencies) || []
  inconsistencies.forEach((inc) => {
    if (inc.is_dismissed || inc.status === 'dismissed' || inc.status === 'resolved') return
    const triggerId = inc.later_evidence_message_id
      ? String(inc.later_evidence_message_id)
      : inc.earlier_evidence_message_id
      ? String(inc.earlier_evidence_message_id)
      : null
    if (triggerId) {
      if (!inconsistenciesByTrigger.has(triggerId)) {
        inconsistenciesByTrigger.set(triggerId, [])
      }
      inconsistenciesByTrigger.get(triggerId).push(inc)
    } else {
      unassignedInconsistencies.push(inc)
    }
  })

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto px-4 py-4 space-y-2 scroll-smooth"
    >
      {/* Load More Button for older messages */}
      {hasMore && (
        <div className="flex justify-center pb-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={onLoadMore}
            className="text-xs text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100"
          >
            <ArrowUp className="w-3.5 h-3.5 mr-1" /> Load older messages
          </Button>
        </div>
      )}

      {/* Message stream with inline AI findings, recommendations, and live context checks */}
      {messages.map((message) => {
        const msgId = message.id ? String(message.id) : null
        const clientId = message.client_id ? String(message.client_id) : null

        const inlineFindings =
          (msgId && findingsByTrigger.get(msgId)) ||
          (clientId && findingsByTrigger.get(clientId)) ||
          []
        const inlineRecs =
          (msgId && recsByTrigger.get(msgId)) ||
          (clientId && recsByTrigger.get(clientId)) ||
          []
        const inlineInconsistencies =
          (msgId && inconsistenciesByTrigger.get(msgId)) ||
          (clientId && inconsistenciesByTrigger.get(clientId)) ||
          []

        return (
          <React.Fragment key={message.id || message.client_id}>
            <MessageBubble message={message} />

            {/* Contextual AI Alignment findings attached to this message */}
            {inlineFindings.map((finding) => (
              <AlignmentFindingCard
                key={finding.id}
                finding={finding}
                onApplyQuestion={onApplyQuestion}
              />
            ))}

            {/* Contextual recommendations attached to this message */}
            {inlineRecs.map((rec) => (
              <div key={rec.id} className="flex justify-start">
                <RecommendationCard recommendation={rec} />
              </div>
            ))}

            {/* Context graph inconsistencies / status checks attached to this message */}
            {inlineInconsistencies.map((inc) => (
              <div key={inc.id} className="flex justify-start w-full">
                <ContextSuggestionCard
                  inconsistency={inc}
                  onClarify={onApplyQuestion}
                  onViewContext={onHighlightEvidence}
                  onDismiss={onDismissInconsistency}
                  onResolve={onResolveInconsistency}
                />
              </div>
            ))}
          </React.Fragment>
        )
      })}

      {/* Unassigned findings (e.g. general conversation analysis) */}
      {unassignedFindings.map((finding) => (
        <AlignmentFindingCard
          key={finding.id}
          finding={finding}
          onApplyQuestion={onApplyQuestion}
        />
      ))}

      {/* Unassigned recommendations */}
      {unassignedRecs.map((rec) => (
        <div key={rec.id} className="flex justify-start">
          <RecommendationCard recommendation={rec} />
        </div>
      ))}

      {/* Unassigned context graph inconsistencies */}
      {unassignedInconsistencies.map((inc) => (
        <div key={inc.id} className="flex justify-start w-full">
          <ContextSuggestionCard
            inconsistency={inc}
            onClarify={onApplyQuestion}
            onViewContext={onHighlightEvidence}
            onDismiss={onDismissInconsistency}
            onResolve={onResolveInconsistency}
          />
        </div>
      ))}

      <div ref={bottomRef} className="h-2" />
    </div>
  )
}
