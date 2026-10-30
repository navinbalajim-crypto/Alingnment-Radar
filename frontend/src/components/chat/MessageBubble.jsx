import React, { useState, useRef } from 'react'
import { formatMessageTime } from '../../utils/date'
import { useAuth } from '../../context/AuthContext'
import { useChat } from '../../context/ChatContext'
import { cn, resolveApiUrl } from '../../utils/helpers'
import {
  Clock,
  AlertCircle,
  ExternalLink,
  Share2,
  Ban,
  MoreVertical,
  Trash2,
  FileText,
  Download,
  Image as ImageIcon,
  Reply,
  Paperclip,
} from 'lucide-react'
import { MeetingInvitationCard } from './MeetingInvitationCard'
import { VoiceMessagePlayer } from './VoiceMessagePlayer'

function formatFileSize(bytes) {
  if (!bytes) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
}

export function MessageBubble({ message }) {
  const { user } = useAuth()
  const { activeEvidenceId, deleteMessage, setReplyTo } = useChat()
  const [showMenu, setShowMenu] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [dragX, setDragX] = useState(0)

  const touchRef = useRef({ startX: 0, startY: 0, isHorizontal: null, active: false })
  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const isSelf = message.sender_id === user?.id || (message.sender_username && message.sender_username === user?.username)
  const isTargetedEvidence = activeEvidenceId && (activeEvidenceId === message.id || activeEvidenceId === message.client_id)

  const isDeletedForEveryone = Boolean(message.is_deleted_for_everyone)
  const isLinkShare = message.message_type === 'link_share'
  const metadata = message.msg_metadata || {}
  const isClarificationRequest = message.message_type === 'ai_alignment' && metadata.kind === 'clarification_request'
  const isMeetingInvitation =
    message.message_type === 'meeting_invitation' || Boolean(metadata.meeting_uri)
  const isVoiceNote =
    message.message_type === 'voice_note' ||
    Boolean(message.voice_transcript) ||
    Boolean(metadata.is_voice_note)
  const attachments = Array.isArray(message.attachments) ? message.attachments : []

  const token = localStorage.getItem('ar_access_token') || ''

  const handleTouchStart = (e) => {
    if (message.isOptimistic || isDeletedForEveryone) return
    const touch = e.touches[0]
    touchRef.current = {
      startX: touch.clientX,
      startY: touch.clientY,
      isHorizontal: null,
      active: true,
    }
  }

  const handleTouchMove = (e) => {
    if (!touchRef.current.active) return
    const touch = e.touches[0]
    const dx = touch.clientX - touchRef.current.startX
    const dy = touch.clientY - touchRef.current.startY

    // Only determine horizontal vs vertical after minimum movement threshold
    if (touchRef.current.isHorizontal === null) {
      if (Math.abs(dx) > 8 || Math.abs(dy) > 8) {
        touchRef.current.isHorizontal = Math.abs(dx) > Math.abs(dy)
      }
    }

    // Never hijack standard vertical scrolling
    if (touchRef.current.isHorizontal === false) {
      return
    }

    // Allow dragging right up to 75px
    if (dx > 0) {
      setDragX(Math.min(dx, 75))
    } else {
      setDragX(0)
    }
  }

  const handleTouchEnd = () => {
    if (!touchRef.current.active) return
    touchRef.current.active = false
    if (dragX >= 45 && setReplyTo) {
      setReplyTo(message)
    }
    setDragX(0)
  }

  const handleDeleteForMe = async (e) => {
    e.stopPropagation()
    setShowMenu(false)
    setIsDeleting(true)
    try {
      await deleteMessage(message.id, 'me')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleDeleteForEveryone = async (e) => {
    e.stopPropagation()
    setShowMenu(false)
    setIsDeleting(true)
    try {
      await deleteMessage(message.id, 'everyone')
    } finally {
      setIsDeleting(false)
    }
  }

  return (
    <div
      id={`msg-${message.id}`}
      className={cn(
        'group flex flex-col my-1 transition-all duration-300 rounded-2xl px-2 py-0.5 relative',
        isSelf ? 'items-end' : 'items-start',
        isTargetedEvidence ? 'highlight-evidence' : ''
      )}
      onTouchStart={handleTouchStart}
      onTouchMove={handleTouchMove}
      onTouchEnd={handleTouchEnd}
    >
      {/* Mobile Swipe-to-reply subtle indicator */}
      {dragX > 0 && (
        <div
          className={cn(
            'absolute left-3 top-1/2 -translate-y-1/2 flex items-center transition-all pointer-events-none z-20',
            dragX >= 45
              ? 'text-apple-blue dark:text-blue-400 scale-115 opacity-100'
              : 'text-neutral-400 opacity-60 scale-90'
          )}
          data-testid="swipe-reply-indicator"
        >
          <Reply className="w-5 h-5 drop-shadow-sm" />
        </div>
      )}

      {/* Sender name for group chats (when message is from other) */}
      {!isSelf && message.sender_username && (
        <span className="text-[11px] font-medium text-neutral-500 dark:text-neutral-400 mb-1 ml-3 select-none">
          @{message.sender_username}
        </span>
      )}

      <div
        style={{
          transform: dragX > 0 ? `translateX(${dragX}px)` : undefined,
          transition: dragX === 0 && !prefersReducedMotion ? 'transform 0.2s cubic-bezier(0.16, 1, 0.3, 1)' : undefined,
        }}
        className={cn(
          'relative max-w-[85%] sm:max-w-[70%] rounded-2xl px-4 py-2.5 shadow-subtle text-sm leading-relaxed transition-all',
          isSelf
            ? 'bg-apple-blue text-white rounded-br-sm'
            : 'bg-white dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 border border-black/[0.04] dark:border-white/[0.06] rounded-bl-sm',
          message.isFailed ? 'border-red-500 bg-red-50 dark:bg-red-950/40 text-red-900 dark:text-red-100' : '',
          isDeletedForEveryone ? 'opacity-80 italic' : ''
        )}
      >
        {/* Message Action menu button and Quick Reply (visible on hover) */}
        {!message.isOptimistic && !isDeletedForEveryone && (
          // Sits beside the bubble (left of outgoing, right of incoming) on its own surface,
          // so it never covers message text or blends into the blue bubble.
          <div
            className={cn(
              'absolute top-1/2 -translate-y-1/2 z-10 flex items-center gap-0.5 rounded-full border border-black/[0.06] dark:border-white/[0.08] bg-white dark:bg-neutral-800 p-0.5 shadow-subtle transition-opacity',
              isSelf ? 'right-full mr-1.5' : 'left-full ml-1.5',
              showMenu ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 focus-within:opacity-100'
            )}
          >
            {/* Desktop quick reply button */}
            <button
              type="button"
              onClick={() => setReplyTo && setReplyTo(message)}
              className="p-1 rounded-full transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500 dark:text-neutral-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue"
              title="Reply"
              aria-label="Reply to message"
              data-testid={`reply-btn-${message.id}`}
            >
              <Reply className="w-3.5 h-3.5" />
            </button>

            {/* More options menu button */}
            <button
              type="button"
              onClick={() => setShowMenu((v) => !v)}
              aria-expanded={showMenu}
              className="p-1 rounded-full transition-colors hover:bg-neutral-100 dark:hover:bg-neutral-700 text-neutral-500 dark:text-neutral-300 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-apple-blue"
              title="Message options"
              aria-label="Message options"
              data-testid={`msg-options-btn-${message.id}`}
            >
              <MoreVertical className="w-3.5 h-3.5" />
            </button>

            {showMenu && (
              <div
                className={cn(
                  'absolute top-8 w-36 rounded-xl bg-white dark:bg-neutral-800 border border-neutral-200 dark:border-neutral-700 shadow-apple py-1 text-xs text-neutral-700 dark:text-neutral-200 z-50 animate-in fade-in zoom-in-95 duration-100',
                  isSelf ? 'right-0' : 'left-0'
                )}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  type="button"
                  onClick={() => {
                    setShowMenu(false)
                    if (setReplyTo) setReplyTo(message)
                  }}
                  className="w-full px-3 py-1.5 text-left hover:bg-neutral-50 dark:hover:bg-neutral-700/50 flex items-center gap-2 transition-colors"
                  data-testid={`menu-reply-btn-${message.id}`}
                >
                  <Reply className="w-3.5 h-3.5 text-neutral-400" />
                  <span>Reply</span>
                </button>

                <button
                  type="button"
                  onClick={handleDeleteForMe}
                  disabled={isDeleting}
                  className="w-full px-3 py-1.5 text-left hover:bg-neutral-50 dark:hover:bg-neutral-700/50 flex items-center gap-2 transition-colors"
                  data-testid="delete-for-me-btn"
                >
                  <Trash2 className="w-3.5 h-3.5 text-neutral-400" />
                  <span>Delete for me</span>
                </button>

                {isSelf && (
                  <button
                    type="button"
                    onClick={handleDeleteForEveryone}
                    disabled={isDeleting}
                    className="w-full px-3 py-1.5 text-left hover:bg-red-50 dark:hover:bg-red-950/30 text-red-600 dark:text-red-400 flex items-center gap-2 transition-colors"
                    data-testid="delete-for-everyone-btn"
                  >
                    <Ban className="w-3.5 h-3.5" />
                    <span>Delete for everyone</span>
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Quoted parent message (if this is a reply) */}
        {message.reply_to && (
          <div
            className={cn(
              'mb-2 p-2 rounded-xl text-xs border-l-4 transition-colors select-none text-left',
              isSelf
                ? 'bg-white/15 border-white/80 text-white'
                : 'bg-neutral-100 dark:bg-neutral-700/60 border-apple-blue dark:border-blue-400 text-neutral-800 dark:text-neutral-200'
            )}
            data-testid={`quoted-reply-${message.reply_to.id}`}
          >
            <div className="font-semibold text-[11px] mb-0.5 opacity-90 flex items-center justify-between gap-2">
              <span>{message.reply_to.sender_username ? `@${message.reply_to.sender_username}` : 'Message'}</span>
              {message.reply_to.has_attachment && !message.reply_to.is_deleted_for_everyone && (
                <span className="flex items-center gap-1 text-[10px] opacity-75">
                  <Paperclip className="w-3 h-3" /> Attachment
                </span>
              )}
            </div>
            <p className="line-clamp-2 italic opacity-85 text-[11px]">
              {message.reply_to.is_deleted_for_everyone
                ? 'This message was deleted.'
                : message.reply_to.content || (message.reply_to.has_attachment ? 'Attachment' : 'Message')}
            </p>
          </div>
        )}

        {/* Deleted for everyone placeholder */}
        {isDeletedForEveryone ? (
          <p className="flex items-center gap-1.5 text-xs opacity-75 select-none" data-testid="deleted-message-indicator">
            <Ban className="w-3.5 h-3.5 opacity-60 shrink-0" />
            <span>This message was deleted.</span>
          </p>
        ) : (
          <>
            {isClarificationRequest && (
              <div data-testid="clarification-request-label" className="text-[10px] font-semibold uppercase tracking-wider opacity-80 mb-1">
                Clarification request
              </div>
            )}

            {/* Special card views or standard text */}
            {isMeetingInvitation ? (
              <MeetingInvitationCard metadata={metadata} message={message} isOwn={isSelf} conversationId={message?.conversation_id} />
            ) : isVoiceNote ? (
              <VoiceMessagePlayer message={message} isOwn={isSelf} />
            ) : isLinkShare ? (
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-1.5 text-xs opacity-80">
                  <Share2 className="w-3.5 h-3.5" />
                  <span className="font-semibold uppercase tracking-wider text-[10px]">
                    Shared {metadata.source || 'Content'}
                  </span>
                </div>

                <p className="font-medium">{message.content}</p>

                {metadata.url && (
                  <a
                    href={metadata.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cn(
                      'mt-1 p-2 rounded-xl text-xs flex items-center justify-between gap-2 border transition-colors',
                      isSelf
                        ? 'bg-white/10 hover:bg-white/20 border-white/20 text-white'
                        : 'bg-neutral-50 dark:bg-neutral-750 hover:bg-neutral-100 border-neutral-200 dark:border-neutral-700 text-apple-blue'
                    )}
                  >
                    <span className="truncate">{metadata.title || metadata.url}</span>
                    <ExternalLink className="w-3 h-3 shrink-0 opacity-70" />
                  </a>
                )}
              </div>
            ) : (
              /* Standard text message */
              message.content && <p className="whitespace-pre-wrap break-words">{message.content}</p>
            )}

            {/* Attached images and documents (exclude voice notes as VoiceMessagePlayer handles audio) */}
            {attachments.length > 0 && !isVoiceNote && (
              <div className="mt-2 space-y-2" data-testid="message-attachments-container">
                {attachments.map((att) => {
                  const isImage = att.content_type?.startsWith('image/')
                  const downloadUrl = resolveApiUrl(`/api/v1/conversations/${message.conversation_id}/attachments/${att.id}${token ? `?token=${encodeURIComponent(token)}` : ''}`)

                  if (isImage) {
                    return (
                      <div key={att.id} className="rounded-xl overflow-hidden border border-black/10 dark:border-white/10 max-w-sm">
                        <img
                          src={downloadUrl}
                          alt={att.original_filename}
                          className="w-full max-h-60 object-cover cursor-pointer hover:opacity-95 transition-opacity"
                          onClick={() => window.open(downloadUrl, '_blank')}
                          data-testid="attachment-image"
                        />
                        <div className="px-2 py-1 text-[11px] opacity-75 truncate bg-black/5 dark:bg-white/5">
                          {att.original_filename} ({formatFileSize(att.file_size)})
                        </div>
                      </div>
                    )
                  }

                  return (
                    <a
                      key={att.id}
                      href={downloadUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      download={att.original_filename}
                      className={cn(
                        'p-2.5 rounded-xl text-xs flex items-center justify-between gap-3 border transition-colors',
                        isSelf
                          ? 'bg-white/10 hover:bg-white/20 border-white/20 text-white'
                          : 'bg-neutral-50 dark:bg-neutral-750 hover:bg-neutral-100 border-neutral-200 dark:border-neutral-700 text-neutral-800 dark:text-neutral-200'
                      )}
                      data-testid="attachment-document"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <FileText className="w-4 h-4 shrink-0 text-apple-blue" />
                        <div className="truncate">
                          <span className="font-medium truncate block">{att.original_filename}</span>
                          <span className="text-[10px] opacity-70">{formatFileSize(att.file_size)}</span>
                        </div>
                      </div>
                      <Download className="w-3.5 h-3.5 shrink-0 opacity-70" />
                    </a>
                  )
                })}
              </div>
            )}
          </>
        )}

        {/* Message footer: timestamp & status */}
        <div
          className={cn(
            'flex items-center justify-end gap-1 mt-1 text-[10px] select-none',
            isSelf ? 'text-white/70' : 'text-neutral-400'
          )}
        >
          <span>{formatMessageTime(message.created_at)}</span>

          {message.isOptimistic && (
            <Clock className="w-2.5 h-2.5 animate-spin" title="Sending..." />
          )}

          {message.isFailed && (
            <span className="flex items-center gap-0.5 text-red-500 font-semibold" title={message.errorMessage || 'Failed to send'}>
              <AlertCircle className="w-3 h-3" /> Failed
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
