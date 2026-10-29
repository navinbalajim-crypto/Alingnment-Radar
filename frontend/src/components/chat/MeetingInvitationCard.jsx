import React, { useState } from 'react'
import { Video, ExternalLink, Copy, Check, Calendar, Sparkles, Plus } from 'lucide-react'
import { meetingService } from '../../services/meetingService'

// Google does not expose live meeting-code status via the API response we store, and a Meet
// conference created this way is capped at 24h by Google's own duration limits, so an invitation
// older than that can no longer be "the same live call" — but we never assert it has expired,
// since only Google knows the actual meeting-code state. We just stop claiming it's live.
const RECENT_CALL_WINDOW_MS = 24 * 60 * 60 * 1000

export function MeetingInvitationCard({ metadata, message, isOwn, conversationId }) {
  const [copied, setCopied] = useState(false)
  const [isStartingNew, setIsStartingNew] = useState(false)

  const meta = metadata || message?.msg_metadata || {}
  const meetingUri = meta.meeting_uri || (message?.content?.startsWith('http') ? message.content : null)
  const meetingCode = meta.meeting_code || 'Google Meet'
  const creatorUsername = meta.creator_username || message?.sender_username || 'Participant'

  const createdAt = message?.created_at ? new Date(message.created_at) : null
  const ageMs = createdAt ? Date.now() - createdAt.getTime() : 0
  const isRecentCall = createdAt ? ageMs < RECENT_CALL_WINDOW_MS : true

  const handleStartNewMeeting = async (e) => {
    e.stopPropagation()
    if (isStartingNew || !conversationId) return
    setIsStartingNew(true)
    try {
      const clientToken = `call_${Date.now()}`
      const result = await meetingService.createMeeting(conversationId, clientToken)
      const authRedirect = result.authorization_url || result.auth_url
      if (result.requires_auth && authRedirect) {
        localStorage.setItem('ar_pending_meet_conversation_id', conversationId)
        window.location.href = authRedirect
        return
      }
      if (result.invitation?.meeting_uri) {
        window.open(result.invitation.meeting_uri, '_blank', 'noopener,noreferrer')
      }
    } catch (err) {
      console.error('Failed to start a new Google Meet call:', err)
    } finally {
      setIsStartingNew(false)
    }
  }

  const handleCopyLink = async (e) => {
    e.stopPropagation()
    if (!meetingUri) return
    try {
      await navigator.clipboard.writeText(meetingUri)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.warn('Clipboard write failed:', err)
    }
  }

  return (
    <div
      className="w-full max-w-sm rounded-2xl overflow-hidden border border-emerald-500/20 bg-gradient-to-br from-emerald-500/10 via-teal-500/5 to-transparent dark:from-emerald-950/40 dark:via-teal-950/20 dark:to-transparent p-4 shadow-sm"
      data-testid="meeting-invitation-card"
    >
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-emerald-600 text-white flex items-center justify-center shadow-subtle shrink-0">
            <Video className="w-5 h-5" />
          </div>
          <div>
            <h4 className="text-sm font-semibold text-neutral-900 dark:text-white leading-tight">
              Google Meet Call
            </h4>
            <p className="text-[11px] text-neutral-500 dark:text-neutral-400">
              Started by @{creatorUsername}
            </p>
          </div>
        </div>
        {isRecentCall ? (
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-300">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            Active Space
          </span>
        ) : (
          <span
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-500 dark:text-neutral-400"
            title="Google Meet links can lapse after long inactivity. Start a new meeting if this one no longer connects."
          >
            Past call
          </span>
        )}
      </div>

      {meetingCode && (
        <div className="mb-3 px-3 py-1.5 rounded-lg bg-black/[0.03] dark:bg-white/[0.04] border border-black/[0.04] dark:border-white/[0.04] flex items-center justify-between text-xs text-neutral-600 dark:text-neutral-300 font-mono">
          <span className="truncate">{meetingCode}</span>
          <span className="text-[10px] text-neutral-400 font-sans">REST v2</span>
        </div>
      )}

      <div className="flex items-center gap-2 pt-1">
        {meetingUri ? (
          <a
            href={meetingUri}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 inline-flex items-center justify-center gap-1.5 px-3.5 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 active:bg-emerald-800 text-white text-xs font-semibold shadow-sm transition-colors text-center"
            data-testid="join-meeting-btn"
          >
            <span>Join Meeting</span>
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        ) : (
          <span className="text-xs text-neutral-400 italic">Link unavailable</span>
        )}

        <button
          type="button"
          onClick={handleCopyLink}
          disabled={!meetingUri}
          className="inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl bg-white dark:bg-neutral-800 hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-700 dark:text-neutral-200 border border-neutral-200 dark:border-neutral-700 text-xs font-medium shadow-sm transition-colors disabled:opacity-50"
          data-testid="copy-meeting-link-btn"
          title={copied ? 'Copied to clipboard!' : 'Copy meeting invitation link'}
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-600" />
              <span className="text-emerald-600 font-medium">Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5 text-neutral-500" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {!isRecentCall && conversationId && (
        <button
          type="button"
          onClick={handleStartNewMeeting}
          disabled={isStartingNew}
          className="mt-2 w-full inline-flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-xl border border-emerald-300/60 dark:border-emerald-700/50 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 text-xs font-medium transition-colors disabled:opacity-50"
          data-testid="start-new-meeting-btn"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>{isStartingNew ? 'Starting...' : 'Start a new meeting'}</span>
        </button>
      )}
    </div>
  )
}
