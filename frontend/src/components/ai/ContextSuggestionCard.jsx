import React, { useState } from 'react'
import { Sparkles, X, CheckCircle2, MessageSquare, ExternalLink } from 'lucide-react'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { cn } from '../../utils/helpers'

export function ContextSuggestionCard({
  inconsistency,
  onClarify,
  onViewContext,
  onDismiss,
  onResolve,
}) {
  const [isDismissing, setIsDismissing] = useState(false)
  const [isResolving, setIsResolving] = useState(false)

  if (
    !inconsistency ||
    inconsistency.is_dismissed ||
    inconsistency.status === 'dismissed' ||
    inconsistency.status === 'resolved'
  ) {
    return null
  }

  const handleDismiss = async () => {
    setIsDismissing(true)
    try {
      await onDismiss?.(inconsistency.id)
    } finally {
      setIsDismissing(false)
    }
  }

  const handleResolve = async () => {
    setIsResolving(true)
    try {
      await onResolve?.(inconsistency.id)
    } finally {
      setIsResolving(false)
    }
  }

  return (
    <div
      className="my-2 p-3.5 rounded-2xl bg-gradient-to-r from-blue-50/70 to-indigo-50/70 dark:from-blue-950/30 dark:to-indigo-950/30 border border-blue-200/60 dark:border-blue-800/40 shadow-subtle text-xs text-neutral-800 dark:text-neutral-200 animate-in fade-in duration-200"
      data-testid="context-suggestion-card"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-lg bg-apple-blue/10 dark:bg-blue-400/20 text-apple-blue dark:text-blue-400 flex items-center justify-center shrink-0">
            <Sparkles className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-neutral-900 dark:text-neutral-100">
                Context Check: {inconsistency.title}
              </span>
              <Badge variant="secondary" className="text-[10px] py-0 px-1.5">
                Live Graph
              </Badge>
            </div>
            {inconsistency.description && (
              <p className="text-[11px] text-neutral-500 dark:text-neutral-400 mt-0.5">
                {inconsistency.description}
              </p>
            )}
          </div>
        </div>

        <button
          type="button"
          onClick={handleDismiss}
          disabled={isDismissing}
          className="text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 p-1 rounded-full transition-colors"
          title="Dismiss suggestion"
          aria-label="Dismiss suggestion"
          data-testid="dismiss-context-suggestion-btn"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {inconsistency.clarification_prompt && (
        <div className="mt-2.5 p-2.5 rounded-xl bg-white/80 dark:bg-neutral-800/80 border border-black/[0.04] dark:border-white/[0.04] font-medium text-neutral-800 dark:text-neutral-200 italic">
          "{inconsistency.clarification_prompt}"
        </div>
      )}

      <div className="mt-3 flex flex-wrap items-center gap-2 pt-1 border-t border-black/[0.04] dark:border-white/[0.04]">
        {inconsistency.clarification_prompt && onClarify && (
          <Button
            size="sm"
            variant="primary"
            onClick={() => onClarify(inconsistency.clarification_prompt)}
            className="text-xs h-7 px-3 bg-apple-blue hover:bg-apple-blue/90 text-white rounded-lg inline-flex items-center gap-1.5 shadow-none"
            data-testid="clarify-context-btn"
          >
            <MessageSquare className="w-3 h-3" /> Clarify this
          </Button>
        )}

        {(inconsistency.earlier_evidence_message_id || inconsistency.later_evidence_message_id) && onViewContext && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              onViewContext(
                inconsistency.earlier_evidence_message_id,
                inconsistency.later_evidence_message_id
              )
            }
            className="text-xs h-7 px-2.5 text-neutral-600 dark:text-neutral-400 hover:text-neutral-900 dark:hover:text-neutral-100 rounded-lg inline-flex items-center gap-1"
            data-testid="view-context-evidence-btn"
          >
            <ExternalLink className="w-3 h-3" /> View evidence
          </Button>
        )}

        <Button
          size="sm"
          variant="ghost"
          onClick={handleResolve}
          disabled={isResolving}
          className="text-xs h-7 px-2.5 text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-950/30 rounded-lg inline-flex items-center gap-1 ml-auto"
          data-testid="resolve-context-btn"
        >
          <CheckCircle2 className="w-3 h-3" /> Resolved
        </Button>
      </div>
    </div>
  )
}
