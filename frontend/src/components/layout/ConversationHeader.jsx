import React, { useState } from 'react'
import { Avatar } from '../ui/Avatar'
import { GroupDetails } from '../groups/GroupDetails'
import { TasksRemindersDialog } from '../chat/TasksRemindersDialog'
import { useChat } from '../../context/ChatContext'
import { meetingService } from '../../services/meetingService'
import { Info, Menu, Compass, Sparkles, Bell, Phone, Loader2, AlertCircle } from 'lucide-react'

export function ConversationHeader({ conversation, onToggleSidebar }) {
  const { socketStatus, triggerAlignment, requestRecommendations, onlineUserIds = new Set(), groupOnlineCounts = {}, presenceReady = false, setMessages } = useChat()
  const [isDetailsOpen, setIsDetailsOpen] = useState(false)
  const [isRemindersOpen, setIsRemindersOpen] = useState(false)
  const [isAnalyzing, setIsAnalyzing] = useState(false)
  const [isRecommending, setIsRecommending] = useState(false)
  const [isCalling, setIsCalling] = useState(false)
  const [callError, setCallError] = useState(null)

  if (!conversation) return null

  const isGroup = conversation.is_group
  const title = isGroup
    ? conversation.title || 'Untitled Group'
    : conversation.other_participant?.display_name ||
      conversation.other_participant?.username ||
      'Direct Message'

  // Presence is only trustworthy once our own socket is connected and the server has sent
  // its presence snapshot; until then the other person's status is unknown, not "online".
  const presenceKnown = socketStatus === 'connected' && presenceReady
  const isOtherOnline = presenceKnown && !isGroup && conversation.other_participant && onlineUserIds.has(conversation.other_participant.id)
  const groupOnlineCount = presenceKnown && isGroup ? groupOnlineCounts[conversation.id] : undefined

  const subtitle = isGroup
    ? `${conversation.member_count || 1} members`
    : conversation.other_participant?.username
    ? `@${conversation.other_participant.username}`
    : 'Direct Chat'

  const presence = isGroup
    ? null
    : !presenceKnown
    ? { dot: null, text: 'Connecting…' }
    : isOtherOnline
    ? { dot: 'bg-emerald-500', text: 'Online' }
    : { dot: 'bg-neutral-300 dark:bg-neutral-600', text: 'Offline' }

  const handleCheckAlignment = async () => {
    if (isAnalyzing || !conversation?.id) return
    setIsAnalyzing(true)
    try {
      await triggerAlignment(conversation.id)
    } catch (err) {
      console.error('Failed to check alignment:', err)
    } finally {
      setIsAnalyzing(false)
    }
  }

  const handleGetRecommendations = async () => {
    if (isRecommending || !conversation?.id) return
    setIsRecommending(true)
    try {
      await requestRecommendations(conversation.id)
    } catch (err) {
      console.error('Failed to get recommendations:', err)
    } finally {
      setIsRecommending(false)
    }
  }

  const handleStartCall = async (instant = false) => {
    const isInstant = instant === true
    if (isCalling || !conversation?.id) return
    setIsCalling(true)
    setCallError(null)

    // Pre-open blank tab synchronously in user click gesture to bypass browser popup blockers
    let popup = null
    try {
      popup = window.open('about:blank', '_blank')
    } catch {
      popup = null
    }

    try {
      const clientToken = `call_${Date.now()}`
      const result = await meetingService.createMeeting(conversation.id, clientToken)
      const authRedirect = result.authorization_url || result.auth_url
      if (result.requires_auth && authRedirect) {
        if (popup && !popup.closed) {
          try { popup.close() } catch {}
        }
        localStorage.setItem('ar_pending_meet_conversation_id', conversation.id)
        window.location.href = authRedirect
        return
      }
      if (result.message && typeof setMessages === 'function') {
        setMessages((prev) => {
          if (prev.some((m) => m && m.id === result.message.id)) return prev
          return [...prev, result.message]
        })
      }

      const targetUri =
        result.invitation?.meeting_uri ||
        result.meeting_uri ||
        result.message?.msg_metadata?.meeting_uri ||
        (result.message?.content?.match(/https?:\/\/[^\s]+/)?.[0])

      if (targetUri) {
        if (popup && !popup.closed) {
          popup.location.href = targetUri
        } else {
          window.open(targetUri, '_blank', 'noopener,noreferrer')
        }
      } else if (popup && !popup.closed) {
        popup.close()
      }
    } catch (err) {
      if (popup && !popup.closed) {
        try { popup.close() } catch {}
      }
      console.error('Failed to create Google Meet call:', err)
      const msg =
        err.response?.data?.message ||
        err.response?.data?.detail ||
        err.message ||
        'Could not create Google Meet meeting.'
      setCallError(msg)
    } finally {
      setIsCalling(false)
    }
  }

  return (
    <>
      <header className="h-16 px-4 flex items-center justify-between border-b border-neutral-200/80 dark:border-neutral-800 bg-white/90 dark:bg-neutral-900/90 backdrop-blur-md z-10 shrink-0">
        <div className="flex items-center gap-3 min-w-0">
          {/* Mobile sidebar drawer trigger */}
          {onToggleSidebar && (
            <button
              type="button"
              onClick={onToggleSidebar}
              className="md:hidden p-2 rounded-xl text-neutral-600 dark:text-neutral-400 hover:bg-neutral-100 dark:hover:bg-neutral-800"
              aria-label="Open conversation list"
            >
              <Menu className="w-5 h-5" />
            </button>
          )}

          <Avatar
            name={title}
            avatarUrl={isGroup ? conversation.avatar_url : conversation.other_participant?.avatar_url}
            isGroup={isGroup}
            size="md"
          />

          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100 truncate">
              {title}
            </h2>
            <div className="flex items-center gap-2 text-xs text-neutral-400">
              <span className="truncate" data-testid="conversation-header-subtitle">
                {subtitle}
                {isGroup && groupOnlineCount > 0 && ` · ${groupOnlineCount} online`}
              </span>
              {presence && (
                <>
                  <span className="text-[10px]">•</span>
                  <span className="flex items-center gap-1.5 shrink-0" data-testid="header-presence">
                    {presence.dot && (
                      <span
                        className={`w-2 h-2 rounded-full ${presence.dot}`}
                        data-testid={isOtherOnline ? 'header-online-dot' : 'header-offline-dot'}
                      />
                    )}
                    <span className={`text-[11px] ${isOtherOnline ? 'text-emerald-600 dark:text-emerald-400' : 'text-neutral-400'}`}>
                      {presence.text}
                    </span>
                  </span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Header Actions: AI Tools & Info */}
        <div className="flex items-center gap-2">
          {/* Google Meet Call Button */}
          <button
            type="button"
            onClick={handleStartCall}
            disabled={isCalling}
            className="px-2.5 py-1.5 rounded-xl border border-emerald-300/80 dark:border-emerald-700/60 bg-emerald-50/80 dark:bg-emerald-950/30 text-emerald-800 dark:text-emerald-200 hover:bg-emerald-100 dark:hover:bg-emerald-900/40 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
            title="Start or create Google Meet video space"
            data-testid="header-call-btn"
            aria-label="Start Google Meet call"
          >
            {isCalling ? (
              <Loader2 className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400 animate-spin" />
            ) : (
              <Phone className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
            )}
            <span className="hidden sm:inline">{isCalling ? 'Connecting...' : 'Meet'}</span>
          </button>

          <button
            type="button"
            onClick={handleCheckAlignment}
            disabled={isAnalyzing}
            className="px-2.5 py-1.5 rounded-xl border border-amber-300/60 dark:border-amber-700/60 bg-amber-50/70 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 hover:bg-amber-100 dark:hover:bg-amber-900/40 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
            title="Scan conversation for communication ambiguity and alignment"
          >
            <Compass className={`w-3.5 h-3.5 text-amber-600 dark:text-amber-400 ${isAnalyzing ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{isAnalyzing ? 'Scanning...' : 'Check Alignment'}</span>
          </button>

          <button
            type="button"
            onClick={handleGetRecommendations}
            disabled={isRecommending}
            className="px-2.5 py-1.5 rounded-xl border border-blue-200/80 dark:border-blue-800/60 bg-blue-50/70 dark:bg-blue-950/30 text-apple-blue dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/40 text-xs font-medium flex items-center gap-1.5 transition-colors disabled:opacity-50"
            title="Fetch contextual recommendations (music, cricket, movies, places)"
          >
            <Sparkles className={`w-3.5 h-3.5 ${isRecommending ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">{isRecommending ? 'Finding...' : 'Recommendations'}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsRemindersOpen(true)}
            className="px-2.5 py-1.5 rounded-xl border border-neutral-200/80 dark:border-neutral-700/80 hover:bg-neutral-100 dark:hover:bg-neutral-800 text-xs font-medium flex items-center gap-1.5 transition-colors"
            title="Conversation Tasks & Reminders"
            data-testid="header-reminders-btn"
          >
            <Bell className="w-3.5 h-3.5 text-neutral-600 dark:text-neutral-400" />
            <span className="hidden sm:inline">Reminders</span>
          </button>

          {isGroup && (
            <button
              type="button"
              onClick={() => setIsDetailsOpen(true)}
              className="p-2 rounded-xl text-neutral-500 hover:text-neutral-900 dark:hover:text-neutral-100 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors flex items-center gap-1 text-xs font-medium"
              title="Group Information and Invitations"
            >
              <Info className="w-4 h-4" />
              <span className="hidden sm:inline">Info & Invites</span>
            </button>
          )}
        </div>
      </header>

      {callError && (
        <div
          className="px-4 py-2 bg-red-50 dark:bg-red-950/40 border-b border-red-200 dark:border-red-900 text-xs text-red-700 dark:text-red-300 flex items-center justify-between"
          data-testid="call-error-banner"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-500 shrink-0" />
            <span>{callError}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handleStartCall(true)}
              className="px-2 py-0.5 rounded bg-emerald-600 text-white font-medium hover:bg-emerald-700 transition-colors"
            >
              Start Instant Meeting
            </button>
            <button
              type="button"
              onClick={() => handleStartCall(false)}
              className="font-medium underline hover:text-red-800 dark:hover:text-red-200"
            >
              Retry
            </button>
            <button
              type="button"
              onClick={() => setCallError(null)}
              className="text-neutral-400 hover:text-neutral-600 dark:hover:text-neutral-200 font-bold ml-2"
            >
              ✕
            </button>
          </div>
        </div>
      )}

      {isGroup && (
        <GroupDetails
          groupId={conversation.id}
          isOpen={isDetailsOpen}
          onClose={() => setIsDetailsOpen(false)}
        />
      )}

      {isRemindersOpen && (
        <TasksRemindersDialog
          conversationId={conversation.id}
          isOpen={isRemindersOpen}
          onClose={() => setIsRemindersOpen(false)}
        />
      )}
    </>
  )
}
