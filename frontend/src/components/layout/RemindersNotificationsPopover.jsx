import React, { useState, useEffect, useCallback } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { reminderService } from '../../services/reminderService'
import { useChat } from '../../context/ChatContext'
import { Bell, Check, Clock, AlertCircle, MessageSquare } from 'lucide-react'
import { formatFullDateTime } from '../../utils/date'

export function RemindersNotificationsPopover({ isOpen, onClose }) {
  const { selectConversation, notifications: realTimeNotifs } = useChat()
  const [notifications, setNotifications] = useState([])
  const [isLoading, setIsLoading] = useState(true)

  const loadNotifications = useCallback(async () => {
    setIsLoading(true)
    try {
      const data = await reminderService.listNotifications()
      setNotifications(Array.isArray(data) ? data : [])
    } catch (err) {
      console.error('Failed to load notifications:', err)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (isOpen) {
      loadNotifications()
    }
  }, [isOpen, loadNotifications, realTimeNotifs])

  const handleMarkRead = async (notifId) => {
    try {
      await reminderService.markNotificationRead(notifId)
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: true } : n))
      )
    } catch (err) {
      console.error('Failed to mark read:', err)
    }
  }

  const handleOpenConversation = (conversationId, notifId) => {
    handleMarkRead(notifId)
    if (conversationId) {
      selectConversation(conversationId)
      onClose()
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Task Notifications"
      description="Scheduled advance warnings and due-time alerts."
      maxWidth="max-w-md"
    >
      <div className="space-y-3" data-testid="reminders-notifications-popover">
        {isLoading ? (
          <div className="py-8 flex flex-col items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-apple-blue border-t-transparent animate-spin mb-2" />
            <p className="text-xs text-neutral-400">Loading alerts...</p>
          </div>
        ) : notifications.length === 0 ? (
          <div className="py-8 text-center text-neutral-400 text-xs">
            No task notifications yet.
          </div>
        ) : (
          <div className="space-y-2 max-h-80 overflow-y-auto">
            {notifications.map((notif) => {
              const isDue = notif.type === 'due_reminder'

              return (
                <div
                  key={notif.id}
                  className={`p-3 rounded-xl border transition-all text-xs ${
                    notif.is_read
                      ? 'bg-neutral-50/50 dark:bg-neutral-900/30 border-neutral-200/50 opacity-70'
                      : isDue
                      ? 'bg-red-50/80 dark:bg-red-950/30 border-red-200 dark:border-red-900/50'
                      : 'bg-amber-50/80 dark:bg-amber-950/30 border-amber-200 dark:border-amber-900/50'
                  }`}
                  data-testid={`notif-item-${notif.id}`}
                >
                  <div className="flex items-start justify-between gap-2 mb-1">
                    <span className="font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-1.5">
                      <Bell className="w-3.5 h-3.5 text-apple-blue shrink-0" />
                      {notif.title}
                    </span>
                    {!notif.is_read && (
                      <span className="w-2 h-2 rounded-full bg-apple-blue shrink-0" />
                    )}
                  </div>

                  <p className="text-neutral-600 dark:text-neutral-300 mb-2 leading-relaxed">
                    {notif.message}
                  </p>

                  <div className="flex items-center justify-between text-[11px] text-neutral-400 pt-1 border-t border-black/5 dark:border-white/5">
                    <span>{formatFullDateTime(notif.created_at)}</span>
                    <div className="flex items-center gap-1">
                      {notif.conversation_id && (
                        <button
                          type="button"
                          onClick={() => handleOpenConversation(notif.conversation_id, notif.id)}
                          className="px-2 py-0.5 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-apple-blue font-medium flex items-center gap-1"
                        >
                          <MessageSquare className="w-3 h-3" />
                          <span>Chat</span>
                        </button>
                      )}
                      {!notif.is_read && (
                        <button
                          type="button"
                          onClick={() => handleMarkRead(notif.id)}
                          className="p-1 rounded-md hover:bg-black/5 dark:hover:bg-white/5 text-neutral-500"
                          title="Mark read"
                        >
                          <Check className="w-3 h-3" />
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </Modal>
  )
}
