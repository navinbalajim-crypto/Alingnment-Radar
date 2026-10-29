import React, { useState } from 'react'
import { Badge } from '../ui/Badge'
import { EvidenceMessageLink } from './EvidenceMessageLink'
import {
  Compass,
  HelpCircle,
  MessageSquarePlus,
  Copy,
  Check,
  Sparkles,
  X,
  CheckCircle2,
  ShieldCheck,
  Clock,
  Users,
  CheckCheck,
} from 'lucide-react'
import { useChat } from '../../context/ChatContext'
import { useAuth } from '../../context/AuthContext'

const CATEGORY_LABELS = {
  ambiguity: 'Communication Ambiguity',
  missing_details: 'Missing Context or Details',
  conflicting_interpretations: 'Conflicting Interpretations',
  unclear_references: 'Unclear Reference or Dependency',
  decision_needed: 'Decision Requiring Confirmation',
  goals: 'Goals & Objectives Divergence',
  scope: 'Scope & Requirements Difference',
  deadlines: 'Timeline & Deadline Discrepancy',
  responsibilities: 'Roles & Responsibilities Mismatch',
  definition_of_done: 'Definition of Done Misalignment',
  other: 'Understanding Difference',
}

export function AlignmentFindingCard({ finding, onApplyQuestion, onDismiss }) {
  const { confirmAlignment, resolveAlignment, dismissAlignment, requestClarification, messages } = useChat()
  const { user } = useAuth()
  const [isRequesting, setIsRequesting] = useState(false)
  const [requestError, setRequestError] = useState('')
  const [copiedQuestion, setCopiedQuestion] = useState(false)
  const [copiedReply, setCopiedReply] = useState(false)
  const [isConfirming, setIsConfirming] = useState(false)
  const [isResolving, setIsResolving] = useState(false)
  const [isDismissing, setIsDismissing] = useState(false)
  const [isDismissedLocally, setIsDismissedLocally] = useState(false)
  const [showClarifyInput, setShowClarifyInput] = useState(false)
  const [clarifyAnswer, setClarifyAnswer] = useState('')
  const [isSubmittingClarification, setIsSubmittingClarification] = useState(false)

  if (!finding || !finding.mismatch_detected || isDismissedLocally || finding.status === 'dismissed') {
    return null
  }

  const status = finding.status || 'detected'
  const categoryLabel = CATEGORY_LABELS[finding.category] || 'Perspective Difference'
  const confidencePercent =
    finding.confidence !== undefined && finding.confidence !== null
      ? Math.round(finding.confidence * 100)
      : null

  const suggestedText = finding.suggested_reply || finding.suggested_rewrite

  const handleCopyQuestion = () => {
    if (finding.clarification_question) {
      navigator.clipboard.writeText(finding.clarification_question)
      setCopiedQuestion(true)
      setTimeout(() => setCopiedQuestion(false), 2000)
    }
  }

  const handleCopyReply = () => {
    if (suggestedText) {
      navigator.clipboard.writeText(suggestedText)
      setCopiedReply(true)
      setTimeout(() => setCopiedReply(false), 2000)
    }
  }

  const handleConfirm = async () => {
    if (isConfirming) return
    setIsConfirming(true)
    try {
      if (confirmAlignment) {
        await confirmAlignment(finding.id, null, finding.conversation_id)
      }
    } catch (err) {
      console.error('Failed to confirm alignment:', err)
    } finally {
      setIsConfirming(false)
    }
  }

  const handleClarifySubmit = async (e) => {
    e?.preventDefault()
    if (!clarifyAnswer.trim() || isSubmittingClarification) return
    setIsSubmittingClarification(true)
    try {
      if (confirmAlignment) {
        await confirmAlignment(finding.id, clarifyAnswer.trim(), finding.conversation_id)
      }
      setClarifyAnswer('')
      setShowClarifyInput(false)
    } catch (err) {
      console.error('Failed to submit clarification:', err)
    } finally {
      setIsSubmittingClarification(false)
    }
  }

  // The author of the flagged message cannot ask themselves; the receiver(s) can.
  const originalId = (finding.supporting_message_ids && finding.supporting_message_ids[0]) || finding.triggered_by_message_id
  const originalMessage = (messages || []).find((m) => m.id === originalId)
  const isAuthor = !!originalMessage && originalMessage.sender_id === user?.id
  const clarificationRequested = !!finding.clarification_request_message_id

  const handleRequestClarification = async () => {
    if (isRequesting || !requestClarification) return
    setIsRequesting(true)
    setRequestError('')
    try {
      await requestClarification(finding.id, finding.conversation_id)
    } catch (err) {
      setRequestError('Could not send the clarification request.')
      console.error('Failed to request clarification:', err)
    } finally {
      setIsRequesting(false)
    }
  }

  const handleManualResolve = async () => {
    if (isResolving) return
    setIsResolving(true)
    try {
      if (resolveAlignment) {
        await resolveAlignment(finding.id, 'Manually marked as resolved by participant', finding.conversation_id)
      }
    } catch (err) {
      console.error('Failed to resolve alignment:', err)
    } finally {
      setIsResolving(false)
    }
  }

  const handleDismiss = async () => {
    setIsDismissedLocally(true)
    if (onDismiss) onDismiss(finding.id)
    if (dismissAlignment) {
      setIsDismissing(true)
      try {
        await dismissAlignment(finding.id, null, finding.conversation_id)
      } catch (err) {
        console.error('Failed to dismiss alignment:', err)
      } finally {
        setIsDismissing(false)
      }
    }
  }

  // Visual theming based on current lifecycle stage
  const isResolved = status === 'resolved'
  const isAwaiting = status === 'awaiting_confirmation'
  const isClarifying = status === 'clarifying'

  let containerStyles =
    'my-3 mx-2 p-4 rounded-2xl border transition-all duration-300 relative shadow-subtle'
  let iconBg = 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
  let IconComponent = Compass
  let badgeVariant = 'amber'
  let statusText = 'Detected'

  if (isResolved) {
    containerStyles +=
      ' bg-emerald-50/80 dark:bg-emerald-950/25 border-emerald-300/80 dark:border-emerald-800/50'
    iconBg = 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
    IconComponent = ShieldCheck
    badgeVariant = 'emerald'
    statusText = 'Alignment Verified'
  } else if (isAwaiting) {
    containerStyles +=
      ' bg-purple-50/80 dark:bg-purple-950/25 border-purple-300/80 dark:border-purple-800/50'
    iconBg = 'bg-purple-500/15 text-purple-600 dark:text-purple-400'
    IconComponent = CheckCircle2
    badgeVariant = 'purple'
    statusText = 'Awaiting Confirmation'
  } else if (isClarifying) {
    containerStyles +=
      ' bg-sky-50/80 dark:bg-sky-950/25 border-sky-300/80 dark:border-sky-800/50'
    iconBg = 'bg-sky-500/15 text-sky-600 dark:text-sky-400'
    IconComponent = Clock
    badgeVariant = 'blue'
    statusText = 'Clarifying in Progress'
  } else {
    containerStyles +=
      ' bg-amber-50/80 dark:bg-amber-950/25 border-amber-200/90 dark:border-amber-800/50'
  }

  return (
    <div className={containerStyles}>
      {/* Header Bar */}
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <div className={`w-6 h-6 rounded-lg ${iconBg} flex items-center justify-center shrink-0`}>
            <IconComponent className="w-3.5 h-3.5" />
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 uppercase tracking-wide">
              {categoryLabel}
            </span>
            {finding.title && (
              <span className="text-xs text-neutral-600 dark:text-neutral-400 font-medium">
                — {finding.title}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant={badgeVariant} size="sm" className="font-semibold">
            {statusText}
          </Badge>

          {finding.severity && !isResolved && (
            <Badge
              variant={
                finding.severity === 'high'
                  ? 'rose'
                  : finding.severity === 'medium'
                  ? 'amber'
                  : 'blue'
              }
              size="sm"
            >
              {finding.severity.toUpperCase()}
            </Badge>
          )}

          {confidencePercent !== null && !isResolved && (
            <Badge variant="neutral" size="sm" className="text-[10px]">
              {confidencePercent}% AI Confidence
            </Badge>
          )}

          <button
            type="button"
            onClick={handleDismiss}
            disabled={isDismissing}
            className="p-1 rounded-md text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 transition-colors"
            title="Dismiss finding"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Primary Issue Explanation */}
      <p className="text-xs text-neutral-800 dark:text-neutral-200 leading-relaxed font-normal">
        {finding.explanation}
      </p>

      {/* Intended Outcome / Goal target */}
      {finding.intended_outcome && (
        <div className="mt-2 text-xs text-neutral-600 dark:text-neutral-400 flex items-center gap-1.5">
          <span className="font-semibold text-[11px] text-neutral-700 dark:text-neutral-300">
            Intended Target:
          </span>
          <span>{finding.intended_outcome}</span>
        </div>
      )}

      {/* Resolution Evidence Box (when in awaiting_confirmation or resolved) */}
      {finding.resolution_evidence && (
        <div className="mt-3 p-3 rounded-xl bg-white/90 dark:bg-neutral-900/80 border border-emerald-200/80 dark:border-emerald-900/50">
          <div className="flex items-center gap-1.5 text-emerald-800 dark:text-emerald-300 font-semibold text-xs mb-1">
            <CheckCheck className="w-4 h-4 text-emerald-600 dark:text-emerald-400" />
            <span>Resolution Evidence</span>
          </div>
          <p className="text-xs text-neutral-700 dark:text-neutral-300 italic">
            "{finding.resolution_evidence}"
          </p>
        </div>
      )}

      {/* Participant Clarification Answers & Confirmations */}
      {finding.confirmations && finding.confirmations.length > 0 && (
        <div className="mt-2.5 space-y-1.5" data-testid="clarification-responses">
          <div className="flex items-center gap-1.5 text-[11px] text-neutral-600 dark:text-neutral-400 font-medium">
            <Users className="w-3.5 h-3.5 text-neutral-500" />
            <span>Participant Responses & Confirmations:</span>
          </div>
          <div className="space-y-1">
            {finding.confirmations.map((c, idx) => (
              <div
                key={c.user_id || idx}
                className="px-2.5 py-1.5 rounded-xl bg-white/90 dark:bg-neutral-800/80 border border-neutral-200/70 dark:border-neutral-700/60 text-xs flex items-start gap-2"
              >
                <Check className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="font-semibold text-neutral-900 dark:text-neutral-100">
                      @{c.username || 'Participant'}
                    </span>
                    {c.confirmed_at && (
                      <span className="text-[10px] text-neutral-400">
                        {new Date(c.confirmed_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    )}
                  </div>
                  {c.comment && (
                    <p className="text-neutral-800 dark:text-neutral-200 mt-0.5 font-medium italic">
                      "{c.comment}"
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Supporting Evidence References */}
      {finding.supporting_message_ids && finding.supporting_message_ids.length > 0 && (
        <div className="mt-2.5 flex items-center flex-wrap gap-1.5 text-xs text-neutral-500">
          <span className="text-[11px] font-medium text-neutral-600 dark:text-neutral-400">
            Referenced Messages:
          </span>
          {finding.supporting_message_ids.map((msgId, idx) => (
            <EvidenceMessageLink key={msgId || idx} messageId={msgId} index={idx} />
          ))}
        </div>
      )}

      {/* Suggested Clarification Question */}
      {finding.clarification_question && !isResolved && (
        <div className="mt-3 p-3 rounded-xl bg-white/85 dark:bg-neutral-900/60 border border-neutral-200/70 dark:border-neutral-800 flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            <HelpCircle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-neutral-500 uppercase tracking-wider">
                Clarification Question
              </p>
              <p className="text-xs text-neutral-800 dark:text-neutral-200 italic mt-0.5 break-words">
                "{finding.clarification_question}"
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {onApplyQuestion && (
              <button
                type="button"
                onClick={() => onApplyQuestion(finding.clarification_question)}
                className="p-1.5 rounded-lg text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200/60 dark:hover:bg-neutral-800 transition-colors"
                title="Paste question into composer"
              >
                <MessageSquarePlus className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              type="button"
              onClick={handleCopyQuestion}
              className="p-1.5 rounded-lg text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200/60 dark:hover:bg-neutral-800 transition-colors"
              title="Copy question"
            >
              {copiedQuestion ? (
                <Check className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>
      )}

      {/* Interactive Clarification Input Form for Both Participants */}
      {showClarifyInput && !isResolved && (
        <form onSubmit={handleClarifySubmit} className="mt-2.5 p-2.5 rounded-xl bg-amber-50/70 dark:bg-amber-950/30 border border-amber-300 dark:border-amber-800/60 space-y-2" data-testid="clarification-form">
          <label className="block text-[11px] font-semibold text-amber-900 dark:text-amber-200">
            Submit Clarification or Answer (Visible to both participants):
          </label>
          <div className="flex items-center gap-1.5">
            <input
              type="text"
              value={clarifyAnswer}
              onChange={(e) => setClarifyAnswer(e.target.value)}
              placeholder="e.g. The report must be uploaded by 5 PM IST tomorrow."
              data-testid="clarification-input"
              className="flex-1 px-2.5 py-1.5 text-xs rounded-lg bg-white dark:bg-neutral-800 border border-neutral-300 dark:border-neutral-700 text-neutral-900 dark:text-neutral-100 focus:outline-none focus:ring-1 focus:ring-amber-500"
            />
            <button
              type="submit"
              disabled={!clarifyAnswer.trim() || isSubmittingClarification}
              data-testid="submit-clarification-btn"
              className="px-2.5 py-1.5 rounded-lg bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold shadow-subtle transition-colors disabled:opacity-50"
            >
              {isSubmittingClarification ? 'Submitting...' : 'Submit'}
            </button>
            <button
              type="button"
              onClick={() => setShowClarifyInput(false)}
              className="p-1 rounded-md text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-300"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </form>
      )}

      {/* Suggested Reply / Rewrite */}
      {suggestedText && !isResolved && (
        <div className="mt-2 p-3 rounded-xl bg-blue-50/70 dark:bg-blue-950/20 border border-blue-200/60 dark:border-blue-900/40 flex items-start justify-between gap-2">
          <div className="flex items-start gap-2 min-w-0">
            <Sparkles className="w-4 h-4 text-apple-blue dark:text-blue-400 shrink-0 mt-0.5" />
            <div className="min-w-0">
              <p className="text-[11px] font-semibold text-apple-blue dark:text-blue-300 uppercase tracking-wider">
                Suggested Alignment Reply
              </p>
              <p className="text-xs text-neutral-800 dark:text-neutral-200 mt-0.5 break-words">
                "{suggestedText}"
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1 shrink-0">
            {onApplyQuestion && (
              <button
                type="button"
                onClick={() => onApplyQuestion(suggestedText)}
                className="p-1.5 rounded-lg text-apple-blue hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors"
                title="Apply reply into composer"
              >
                <MessageSquarePlus className="w-3.5 h-3.5" />
              </button>
            )}
            <button
              type="button"
              onClick={handleCopyReply}
              className="p-1.5 rounded-lg text-neutral-600 dark:text-neutral-300 hover:bg-neutral-200/60 dark:hover:bg-neutral-800 transition-colors"
              title="Copy suggested reply"
            >
              {copiedReply ? (
                <Check className="w-3.5 h-3.5 text-emerald-600" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
            </button>
          </div>
        </div>
      )}

      {/* Action Bar */}
      {!isResolved && (
        <div className="mt-3 pt-2.5 border-t border-neutral-200/60 dark:border-neutral-800/80 flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowClarifyInput((v) => !v)}
              data-testid="clarify-answer-toggle-btn"
              className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-amber-500 text-white hover:bg-amber-600 shadow-subtle transition-colors"
            >
              <HelpCircle className="w-3 h-3" />
              <span>{showClarifyInput ? 'Close Answer' : 'Answer'}</span>
            </button>

            {!isAuthor && !clarificationRequested && (
              <button
                type="button"
                onClick={handleRequestClarification}
                disabled={isRequesting}
                data-testid="request-clarification-btn"
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-sky-600 text-white hover:bg-sky-700 shadow-subtle transition-colors disabled:opacity-50"
              >
                <MessageSquarePlus className="w-3 h-3" />
                <span>{isRequesting ? 'Sending...' : 'Ask for clarification'}</span>
              </button>
            )}
            {clarificationRequested && (
              <span data-testid="clarification-requested" className="text-xs font-medium text-sky-700 dark:text-sky-300">
                Clarification requested
              </span>
            )}
            {requestError && <span className="text-xs text-red-600">{requestError}</span>}

            {finding.clarification_question && onApplyQuestion && (
              <button
                type="button"
                onClick={() => onApplyQuestion(finding.clarification_question)}
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-white dark:bg-neutral-800 text-neutral-800 dark:text-neutral-200 border border-neutral-200 dark:border-neutral-700 hover:bg-neutral-50 shadow-subtle transition-colors"
              >
                <MessageSquarePlus className="w-3 h-3 text-amber-500" />
                <span>Clarify</span>
              </button>
            )}

            {suggestedText && onApplyQuestion && (
              <button
                type="button"
                onClick={() => onApplyQuestion(suggestedText)}
                className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-blue-500 text-white hover:bg-blue-600 shadow-subtle transition-colors"
              >
                <Sparkles className="w-3 h-3" />
                <span>Suggest Reply</span>
              </button>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleConfirm}
              disabled={isConfirming}
              className="inline-flex items-center gap-1 text-xs font-semibold px-2.5 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white shadow-subtle transition-colors disabled:opacity-50"
            >
              <Check className="w-3 h-3" />
              <span>{isConfirming ? 'Confirming...' : 'Confirm Alignment'}</span>
            </button>

            <button
              type="button"
              onClick={handleManualResolve}
              disabled={isResolving}
              className="text-xs text-neutral-500 hover:text-neutral-800 dark:hover:text-neutral-300 font-medium transition-colors"
              title="Manually mark resolved"
            >
              Resolve
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

