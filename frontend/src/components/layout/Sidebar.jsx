import React, { useState, useEffect } from 'react'
import { ConversationItem } from '../chat/ConversationItem'
import { CreateGroupDialog } from '../groups/CreateGroupDialog'
import { UserSearchDialog } from './UserSearchDialog'
import { IntegrationsDialog } from '../settings/IntegrationsDialog'
import { GmailNotificationsPopover } from './GmailNotificationsPopover'
import { RemindersNotificationsPopover } from './RemindersNotificationsPopover'
import { Avatar } from '../ui/Avatar'
import { useAuth } from '../../context/AuthContext'
import { useChat } from '../../context/ChatContext'
import { gmailService } from '../../services/gmailService'
import { reminderService } from '../../services/reminderService'
import { authService } from '../../services/authService'
import {
  Compass,
  Plus,
  Search,
  MessageSquare,
  LogOut,
  X,
  Sliders,
  Mail,
  Bell,
  Camera,
} from 'lucide-react'

export function Sidebar({ onCloseMobile }) {
  const { user, setUser, logout } = useAuth()
  const { conversations, activeConversationId, selectConversation, notifications: realTimeNotifs } = useChat()

  const [filterQuery, setFilterQuery] = useState('')
  const [isCreateGroupOpen, setIsCreateGroupOpen] = useState(false)
  const [isSearchUserOpen, setIsSearchUserOpen] = useState(false)
  const [isIntegrationsOpen, setIsIntegrationsOpen] = useState(false)
  const [isGmailOpen, setIsGmailOpen] = useState(false)
  const [isRemindersOpen, setIsRemindersOpen] = useState(false)
  const [unreadGmailCount, setUnreadGmailCount] = useState(0)
  const [unreadRemindersCount, setUnreadRemindersCount] = useState(0)
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false)
  const [avatarError, setAvatarError] = useState(null)

  const handleAvatarFileChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setAvatarError(null)
    setIsUploadingAvatar(true)
    try {
      const updatedUser = await authService.uploadAvatar(file)
      setUser(updatedUser)
    } catch (err) {
      setAvatarError(err.response?.data?.detail || err.response?.data?.message || 'Failed to update profile picture.')
    } finally {
      setIsUploadingAvatar(false)
    }
  }

  // Fetch unread task notifications
  useEffect(() => {
    let isMounted = true
    const checkReminders = async () => {
      try {
        const notifs = await reminderService.listNotifications({ unreadOnly: true })
        if (isMounted) {
          setUnreadRemindersCount(Array.isArray(notifs) ? notifs.length : 0)
        }
      } catch {
        // ignore
      }
    }
    checkReminders()
    const interval = setInterval(checkReminders, 30000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [isRemindersOpen, realTimeNotifs])

  // Fetch unread Gmail notifications on mount and interval
  useEffect(() => {
    let isMounted = true
    const checkGmail = async () => {
      try {
        const status = await gmailService.getStatus()
        if (isMounted && status?.connected) {
          setUnreadGmailCount(status.unread_notifications_count || 0)
        }
      } catch {
        // silently ignore if not connected
      }
    }

    checkGmail()
    const interval = setInterval(checkGmail, 60000)
    return () => {
      isMounted = false
      clearInterval(interval)
    }
  }, [isGmailOpen, isIntegrationsOpen])

  // Separate direct messages and group conversations
  const directConversations = conversations.filter((c) => !c.is_group)
  const groupConversations = conversations.filter((c) => c.is_group)

  const filterItem = (conv) => {
    if (!filterQuery.trim()) return true
    const q = filterQuery.toLowerCase()
    const title = conv.is_group
      ? conv.title
      : conv.other_participant?.display_name || conv.other_participant?.username
    return title?.toLowerCase().includes(q)
  }

  const filteredDMs = directConversations.filter(filterItem)
  const filteredGroups = groupConversations.filter(filterItem)

  const handleSelect = (convId) => {
    selectConversation(convId)
    if (onCloseMobile) {
      onCloseMobile()
    }
  }

  return (
    <>
      <aside className="w-80 h-full flex flex-col bg-white dark:bg-neutral-900 border-r border-neutral-200/80 dark:border-neutral-800 shrink-0 select-none">
        {/* Brand & Action Header */}
        <div className="p-4 border-b border-neutral-100 dark:border-neutral-800 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-neutral-900 dark:bg-white flex items-center justify-center text-white dark:text-neutral-900 shadow-subtle">
              <Compass className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-sm font-bold tracking-tight text-neutral-900 dark:text-white leading-none">
                Alignment Radar
              </h1>
              <span className="text-[10px] text-neutral-400 font-medium">
                AI Real-Time Chat
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setIsSearchUserOpen(true)}
              className="p-1.5 rounded-lg text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              title="Start New Direct Chat"
            >
              <MessageSquare className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={() => setIsCreateGroupOpen(true)}
              className="p-1.5 rounded-lg text-neutral-600 dark:text-neutral-300 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
              title="Create New Group"
            >
              <Plus className="w-4 h-4" />
            </button>

            {onCloseMobile && (
              <button
                type="button"
                onClick={onCloseMobile}
                className="md:hidden p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700"
              >
                <X className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Search / Filter bar */}
        <div className="px-3 pt-3 pb-2">
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 text-neutral-400 absolute left-3 pointer-events-none" />
            <input
              type="text"
              placeholder="Filter chats & groups..."
              value={filterQuery}
              onChange={(e) => setFilterQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 text-xs bg-neutral-100 dark:bg-neutral-800 text-neutral-900 dark:text-neutral-100 placeholder-neutral-400 rounded-xl border border-transparent focus:outline-none focus:border-apple-blue transition-all"
            />
          </div>
        </div>

        {/* Conversation list with sections */}
        <div className="flex-1 overflow-y-auto px-2 py-2 space-y-4">
          {/* Direct Messages Section */}
          <div>
            <div className="flex items-center justify-between px-2 mb-1.5">
              <span className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
                Direct Messages
              </span>
              <button
                type="button"
                onClick={() => setIsSearchUserOpen(true)}
                className="text-[11px] text-apple-blue hover:underline"
              >
                + New Chat
              </button>
            </div>

            {filteredDMs.length > 0 ? (
              <div className="space-y-0.5">
                {filteredDMs.map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isSelected={activeConversationId === conv.id}
                    onClick={() => handleSelect(conv.id)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-xs text-neutral-400 px-3 py-2 italic">
                {filterQuery ? 'No matching chats' : 'No direct chats yet'}
              </p>
            )}
          </div>

          {/* Group Conversations Section */}
          <div>
            <div className="flex items-center justify-between px-2 mb-1.5">
              <span className="text-[11px] font-semibold text-neutral-400 uppercase tracking-wider">
                Groups
              </span>
              <button
                type="button"
                onClick={() => setIsCreateGroupOpen(true)}
                className="text-[11px] text-apple-blue hover:underline"
              >
                + New Group
              </button>
            </div>

            {filteredGroups.length > 0 ? (
              <div className="space-y-0.5">
                {filteredGroups.map((conv) => (
                  <ConversationItem
                    key={conv.id}
                    conversation={conv}
                    isSelected={activeConversationId === conv.id}
                    onClick={() => handleSelect(conv.id)}
                  />
                ))}
              </div>
            ) : (
              <p className="text-xs text-neutral-400 px-3 py-2 italic">
                {filterQuery ? 'No matching groups' : 'No group chats yet'}
              </p>
            )}
          </div>
        </div>

        {/* Bottom Current User Profile & Sign Out */}
        {user && (
          <div className="flex flex-col border-t border-neutral-100 dark:border-neutral-800">
          {avatarError && (
            <div className="px-3 pt-2 text-[11px] text-red-600 dark:text-red-400" data-testid="avatar-upload-error">
              {avatarError}
            </div>
          )}
          <div className="p-3 flex items-center justify-between bg-neutral-50/70 dark:bg-neutral-850/50">
            <div className="flex items-center gap-2.5 min-w-0">
              <label
                className="relative group/avatar rounded-full cursor-pointer shrink-0"
                title="Change profile picture"
                data-testid="change-avatar-label"
              >
                <Avatar name={user.display_name || user.username} avatarUrl={user.avatar_url} size="sm" />
                <span className="absolute inset-0 rounded-full bg-black/0 group-hover/avatar:bg-black/40 transition-colors flex items-center justify-center">
                  <Camera className="w-3 h-3 text-white opacity-0 group-hover/avatar:opacity-100 transition-opacity" />
                </span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={handleAvatarFileChange}
                  disabled={isUploadingAvatar}
                  data-testid="avatar-file-input"
                />
              </label>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                  {user.display_name || user.username}
                </p>
                <p className="text-[11px] text-neutral-400 truncate">
                  @{user.username}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setIsRemindersOpen(true)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors relative"
                title="Task & Deadline Reminders"
                data-testid="sidebar-reminders-btn"
              >
                <Bell className="w-4 h-4" />
                {unreadRemindersCount > 0 && (
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-apple-blue ring-2 ring-white dark:ring-neutral-900" />
                )}
              </button>
              <button
                type="button"
                onClick={() => setIsGmailOpen(true)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors relative"
                title="Gmail Notifications"
              >
                <Mail className="w-4 h-4" />
                {unreadGmailCount > 0 && (
                  <span className="absolute top-1 right-1 w-2 h-2 rounded-full bg-red-500 ring-2 ring-white dark:ring-neutral-900" />
                )}
              </button>
              <button
                type="button"
                onClick={() => setIsIntegrationsOpen(true)}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-neutral-700 dark:hover:text-neutral-200 hover:bg-neutral-100 dark:hover:bg-neutral-800 transition-colors"
                title="Google Integrations & Privacy"
              >
                <Sliders className="w-4 h-4" />
              </button>
              <button
                type="button"
                onClick={logout}
                className="p-1.5 rounded-lg text-neutral-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40 transition-colors"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          </div>
          </div>
        )}
      </aside>

      {/* Modals */}
      <CreateGroupDialog
        isOpen={isCreateGroupOpen}
        onClose={() => setIsCreateGroupOpen(false)}
      />
      <UserSearchDialog
        isOpen={isSearchUserOpen}
        onClose={() => setIsSearchUserOpen(false)}
        onOpenSettings={() => setIsIntegrationsOpen(true)}
      />
      <IntegrationsDialog
        isOpen={isIntegrationsOpen}
        onClose={() => setIsIntegrationsOpen(false)}
      />
      <GmailNotificationsPopover
        isOpen={isGmailOpen}
        onClose={() => setIsGmailOpen(false)}
        onOpenSettings={() => setIsIntegrationsOpen(true)}
      />
      <RemindersNotificationsPopover
        isOpen={isRemindersOpen}
        onClose={() => setIsRemindersOpen(false)}
      />
    </>
  )
}

