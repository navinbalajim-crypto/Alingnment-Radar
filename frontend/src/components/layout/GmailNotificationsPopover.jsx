import React, { useState, useEffect } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { gmailService } from '../../services/gmailService'
import {
  Mail,
  RefreshCw,
  CheckCheck,
  Sliders,
  AlertCircle,
  Clock,
} from 'lucide-react'

export function GmailNotificationsPopover({ isOpen, onClose, onOpenSettings }) {
  const [status, setStatus] = useState(null)
  const [notifications, setNotifications] = useState([])
  const [unreadCount, setUnreadCount] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [isChecking, setIsChecking] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!isOpen) return
    loadData()
  }, [isOpen])

  const loadData = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const gStatus = await gmailService.getStatus().catch(() => ({ connected: false }))
      setStatus(gStatus)
      if (gStatus.connected) {
        const notifData = await gmailService.getNotifications(30, 0, false)
        setNotifications(notifData.notifications || [])
        setUnreadCount(notifData.unread_count || 0)
      }
    } catch (err) {
      setError('Failed to load Gmail notifications.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCheckNow = async () => {
    setIsChecking(true)
    setError(null)
    try {
      await gmailService.checkMessages()
      await loadData()
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to check Gmail.')
    } finally {
      setIsChecking(false)
    }
  }

  const handleMarkRead = async (notifId) => {
    try {
      await gmailService.markAsRead(notifId)
      setNotifications((prev) =>
        prev.map((n) => (n.id === notifId ? { ...n, is_read: true } : n))
      )
      setUnreadCount((prev) => Math.max(0, prev - 1))
    } catch {
      // silently ignore
    }
  }

  const handleMarkAllRead = async () => {
    try {
      await gmailService.markAllAsRead()
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })))
      setUnreadCount(0)
    } catch {
      // silently ignore
    }
  }

  const formatTime = (isoStr) => {
    if (!isoStr) return ''
    try {
      const d = new Date(isoStr)
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return ''
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Gmail Inbox Notifications"
      description="In-app alerts for incoming emails. Read-only metadata only."
      maxWidth="max-w-lg"
    >
      <div className="flex flex-col gap-3 py-1">
        {error && (
          <div className="p-2.5 rounded-xl bg-red-50 dark:bg-red-950/40 text-red-600 dark:text-red-400 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {!status?.connected ? (
          <div className="p-6 text-center rounded-2xl bg-neutral-50 dark:bg-neutral-850/60 border border-neutral-200/80 dark:border-neutral-800 flex flex-col items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-red-50 dark:bg-red-950/50 text-red-500 flex items-center justify-center">
              <Mail className="w-6 h-6" />
            </div>
            <div className="space-y-1 max-w-sm">
              <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                Gmail Not Connected
              </h3>
              <p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed">
                Connect your Google account in Settings to receive in-app alerts when important new emails arrive. We only access email headers (Subject, From, Date) — never the body, and never sent to AI models.
              </p>
            </div>
            <Button
              size="sm"
              variant="primary"
              onClick={() => {
                onClose()
                if (onOpenSettings) onOpenSettings()
              }}
              className="text-xs py-2 px-4"
            >
              <Sliders className="w-3.5 h-3.5 mr-1.5" />
              Configure in Settings
            </Button>
          </div>
        ) : (
          <>
            {/* Action Bar */}
            <div className="flex items-center justify-between px-1">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200">
                  Recent Alerts
                </span>
                {unreadCount > 0 && (
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-100 text-red-600 dark:bg-red-950/60 dark:text-red-400">
                    {unreadCount} unread
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1.5">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleCheckNow}
                  isLoading={isChecking}
                  className="text-xs py-1 px-2.5"
                  title="Scan Gmail for new messages"
                >
                  <RefreshCw className={`w-3.5 h-3.5 mr-1 ${isChecking ? 'animate-spin' : ''}`} />
                  Check Mail
                </Button>

                {unreadCount > 0 && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={handleMarkAllRead}
                    className="text-xs py-1 px-2.5 text-neutral-500 hover:text-neutral-900 dark:hover:text-white"
                    title="Mark all as read"
                  >
                    <CheckCheck className="w-3.5 h-3.5 mr-1" />
                    Read All
                  </Button>
                )}
              </div>
            </div>

            {/* List */}
            <div className="max-h-72 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-xl border border-neutral-100 dark:border-neutral-800">
              {isLoading ? (
                <div className="p-6 text-center text-xs text-neutral-400">
                  Loading Gmail alerts...
                </div>
              ) : notifications.length > 0 ? (
                notifications.map((n) => (
                  <div
                    key={n.id}
                    onClick={() => !n.is_read && handleMarkRead(n.id)}
                    className={`p-3 transition-colors cursor-pointer flex items-start gap-3 ${
                      n.is_read
                        ? 'hover:bg-neutral-50 dark:hover:bg-neutral-800/40 opacity-75'
                        : 'bg-blue-50/40 dark:bg-blue-950/20 hover:bg-blue-50/70 dark:hover:bg-blue-950/30'
                    }`}
                  >
                    <div className="mt-1">
                      {n.is_read ? (
                        <div className="w-2 h-2 rounded-full bg-neutral-300 dark:bg-neutral-700" />
                      ) : (
                        <div className="w-2 h-2 rounded-full bg-apple-blue shadow-[0_0_6px_rgba(0,122,255,0.6)]" />
                      )}
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                          {n.sender || 'Unknown Sender'}
                        </p>
                        <span className="text-[10px] text-neutral-400 shrink-0 flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {formatTime(n.received_at || n.created_at)}
                        </span>
                      </div>

                      <p className="text-xs font-medium text-neutral-800 dark:text-neutral-200 truncate mt-0.5">
                        {n.subject || '(No Subject)'}
                      </p>

                      {n.snippet && (
                        <p className="text-[11px] text-neutral-500 dark:text-neutral-400 line-clamp-1 mt-0.5">
                          {n.snippet}
                        </p>
                      )}
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-8 text-center text-xs text-neutral-400 space-y-1">
                  <p>No email notifications yet.</p>
                  <p className="text-[11px]">Click "Check Mail" above to poll for recent messages.</p>
                </div>
              )}
            </div>

            <div className="flex items-center justify-between pt-1 text-[11px] text-neutral-400 px-1">
              <span>Account: {status.email || 'Connected'}</span>
              <button
                type="button"
                onClick={() => {
                  onClose()
                  if (onOpenSettings) onOpenSettings()
                }}
                className="text-apple-blue hover:underline"
              >
                Manage Permissions
              </button>
            </div>
          </>
        )}
      </div>
    </Modal>
  )
}
