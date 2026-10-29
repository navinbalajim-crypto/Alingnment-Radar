import React, { useEffect, useState } from 'react'
import { Avatar } from '../ui/Avatar'
import { formatConversationTime } from '../../utils/date'
import { cn } from '../../utils/helpers'
import { useChat } from '../../context/ChatContext'

export function ConversationItem({ conversation, isSelected, onClick }) {
  // Relative labels ("Yesterday", weekday, time) can go stale while the app
  // stays open; re-render once a minute so they stay accurate without a page reload.
  const [, forceTick] = useState(0)
  useEffect(() => {
    const interval = setInterval(() => forceTick((t) => t + 1), 60000)
    return () => clearInterval(interval)
  }, [])

  const { onlineUserIds = new Set(), groupOnlineCounts = {} } = useChat()
  const isGroup = conversation.is_group
  const isOtherOnline = !isGroup && conversation.other_participant && onlineUserIds.has(conversation.other_participant.id)
  const groupOnlineCount = isGroup ? groupOnlineCounts[conversation.id] : undefined
  const title = isGroup
    ? conversation.title || 'Untitled Group'
    : conversation.other_participant?.display_name ||
      conversation.other_participant?.username ||
      'Direct Message'
  const lastMessage = conversation.last_message
  const lastMessageText = lastMessage
    ? lastMessage.message_type === 'link_share'
      ? `🔗 Shared ${lastMessage.msg_metadata?.source || 'content'}`
      : lastMessage.content
    : 'No messages yet'

  const timeDisplay = formatConversationTime(
    lastMessage?.created_at || conversation.updated_at
  )

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-3 px-3 py-2.5 rounded-2xl transition-all duration-150 text-left select-none group',
        isSelected
          ? 'bg-neutral-200/80 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-50 shadow-subtle'
          : 'hover:bg-neutral-100 dark:hover:bg-neutral-800/50 text-neutral-700 dark:text-neutral-300'
      )}
    >
      <div className="relative shrink-0">
        <Avatar
          name={title}
          avatarUrl={isGroup ? conversation.avatar_url : conversation.other_participant?.avatar_url}
          isGroup={isGroup}
          size="md"
          className={isSelected ? 'ring-2 ring-apple-blue/30' : ''}
        />
        {isOtherOnline && (
          <span
            className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-white dark:ring-neutral-900"
            data-testid="online-status-dot"
            title="Online"
          />
        )}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-1">
          <span
            className={cn(
              'text-sm truncate font-medium',
              isSelected ? 'font-semibold text-neutral-900 dark:text-white' : ''
            )}
          >
            {title}
          </span>
          {timeDisplay && (
            <span className="text-[11px] text-neutral-400 shrink-0 font-normal">
              {timeDisplay}
            </span>
          )}
        </div>

        <div className="flex items-center justify-between gap-1 mt-0.5">
          <p className="text-xs text-neutral-500 dark:text-neutral-400 truncate leading-tight">
            {lastMessageText}
          </p>
          {isGroup && groupOnlineCount > 0 && (
            <span
              className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium shrink-0"
              data-testid="group-online-count"
            >
              {groupOnlineCount} online
            </span>
          )}
        </div>
      </div>
    </button>
  )
}
