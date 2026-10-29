import React, { useState, useEffect } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { GoogleButton } from '../ui/GoogleButton'
import { gmailService } from '../../services/gmailService'
import {
  Mail,
  ShieldCheck,
  RefreshCw,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Info,
} from 'lucide-react'

export function IntegrationsDialog({ isOpen, onClose }) {
  const [gmailStatus, setGmailStatus] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(null) // 'check_gmail' | 'disconnect_gmail'
  const [error, setError] = useState(null)
  const [successMsg, setSuccessMsg] = useState(null)

  useEffect(() => {
    if (!isOpen) return
    loadStatuses()
  }, [isOpen])

  const loadStatuses = async () => {
    setIsLoading(true)
    setError(null)
    try {
      const gStatus = await gmailService.getStatus().catch(() => ({ connected: false }))
      setGmailStatus(gStatus)
    } catch (err) {
      setError('Failed to fetch integration statuses.')
    } finally {
      setIsLoading(false)
    }
  }

  const handleCheckGmail = async () => {
    setActionLoading('check_gmail')
    setError(null)
    setSuccessMsg(null)
    try {
      const res = await gmailService.checkMessages()
      setSuccessMsg(res.message || 'Checked Gmail for new messages.')
      await loadStatuses()
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to check Gmail.')
    } finally {
      setActionLoading(null)
    }
  }

  const handleDisconnectGmail = async () => {
    if (!window.confirm('Disconnect Gmail integration? New mail notifications will stop.')) return
    setActionLoading('disconnect_gmail')
    setError(null)
    setSuccessMsg(null)
    try {
      await gmailService.disconnect()
      setSuccessMsg('Gmail notifications disconnected successfully.')
      await loadStatuses()
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to disconnect Gmail.')
    } finally {
      setActionLoading(null)
    }
  }

  const formatTimestamp = (isoStr) => {
    if (!isoStr) return 'Never'
    try {
      const d = new Date(isoStr)
      return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    } catch {
      return isoStr
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Google Integrations & Privacy"
      description="Manage your connected Google services independently with granular privacy controls."
      maxWidth="max-w-xl"
    >
      <div className="flex flex-col gap-5 py-1">
        {error && (
          <div className="flex items-start gap-2.5 p-3 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-red-600 dark:text-red-400 text-xs">
            <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1 space-y-2">
              <p className="leading-relaxed">{error}</p>
              {error.includes('https://') && (
                <div>
                  <a
                    href={error.match(/https:\/\/[^\s]+/)?.[0]}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg bg-red-100 dark:bg-red-900/50 hover:bg-red-200 dark:hover:bg-red-900/80 text-red-700 dark:text-red-300 font-medium text-[11px] transition-colors underline underline-offset-2"
                  >
                    Open Google Cloud Console to Enable API &rarr;
                  </a>
                </div>
              )}
            </div>
          </div>
        )}

        {successMsg && (
          <div className="flex items-start gap-2.5 p-3 rounded-xl bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-600 dark:text-emerald-400 text-xs">
            <CheckCircle2 className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="flex-1">{successMsg}</div>
          </div>
        )}

        {/* Gmail Notifications */}
        <div className="p-4 rounded-2xl bg-neutral-50 dark:bg-neutral-850/60 border border-neutral-200/80 dark:border-neutral-800 flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-xl bg-red-500/10 dark:bg-red-500/20 text-red-500 flex items-center justify-center">
                <Mail className="w-4.5 h-4.5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-neutral-900 dark:text-white">
                  Gmail Inbox Notifications
                </h3>
                <p className="text-[11px] text-neutral-400">
                  Receive in-app alerts when important new emails arrive
                </p>
              </div>
            </div>

            {gmailStatus?.connected ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                Connected
              </span>
            ) : (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-neutral-100 dark:bg-neutral-800 text-neutral-500">
                Disconnected
              </span>
            )}
          </div>

          <div className="text-xs text-neutral-600 dark:text-neutral-400 leading-relaxed bg-white/60 dark:bg-neutral-900/40 p-3 rounded-xl border border-neutral-100 dark:border-neutral-800/80 space-y-1.5">
            <div className="flex items-center gap-1.5 text-[11px] font-medium text-neutral-700 dark:text-neutral-300">
              <ShieldCheck className="w-3.5 h-3.5 text-apple-blue" />
              <span>Strict Zero-AI & Metadata Privacy Guarantee:</span>
            </div>
            <p className="text-[11px]">
              Requests minimum read-only scope (<code className="text-[10px] bg-neutral-100 dark:bg-neutral-800 px-1 py-0.5 rounded">gmail.metadata</code>). Only email headers (Subject, From, Date, and Snippet) are read for in-app alert banners. Email bodies are never read or stored, and Gmail contents are <strong>strictly never sent to external AI providers (NVIDIA NIM, Groq)</strong>.
            </p>
            <div className="flex items-start gap-1.5 text-[10.5px] text-neutral-500 dark:text-neutral-400 pt-1">
              <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
              <span>
                Delivery Mode: Rate-limited background polling (60s). Instant push notifications require Google Cloud Pub/Sub topic configuration.
              </span>
            </div>
            {gmailStatus?.connected && (
              <div className="pt-2 border-t border-neutral-100 dark:border-neutral-800 grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <span className="text-neutral-400">Google Account: </span>
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">{gmailStatus.email || 'Authorized'}</span>
                </div>
                <div>
                  <span className="text-neutral-400">Unread Alerts: </span>
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">{gmailStatus.unread_notifications_count}</span>
                </div>
                <div>
                  <span className="text-neutral-400">Last Checked: </span>
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">{formatTimestamp(gmailStatus.last_checked_at)}</span>
                </div>
                <div>
                  <span className="text-neutral-400">Mechanism: </span>
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">{gmailStatus.delivery_mechanism}</span>
                </div>
              </div>
            )}
          </div>

          <div className="flex items-center justify-end gap-2 pt-1">
            {gmailStatus?.connected ? (
              <>
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={handleCheckGmail}
                  isLoading={actionLoading === 'check_gmail'}
                  className="text-xs py-1.5 px-3"
                >
                  <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${actionLoading === 'check_gmail' ? 'animate-spin' : ''}`} />
                  Check for Mail
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={handleDisconnectGmail}
                  isLoading={actionLoading === 'disconnect_gmail'}
                  className="text-xs py-1.5 px-3 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/40"
                >
                  <Trash2 className="w-3.5 h-3.5 mr-1.5" />
                  Disconnect
                </Button>
              </>
            ) : (
              <GoogleButton
                label="Connect Gmail Notifications"
                className="w-auto py-1.5 px-4"
                getAuthUrl={gmailService.getConnectUrl}
                onError={(err) => setError(err)}
              />
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
