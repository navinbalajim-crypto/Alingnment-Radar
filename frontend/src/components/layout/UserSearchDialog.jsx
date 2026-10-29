import React, { useState, useEffect } from 'react'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { Avatar } from '../ui/Avatar'
import { Button } from '../ui/Button'
import { GoogleButton } from '../ui/GoogleButton'
import { authService } from '../../services/authService'
import { contactService } from '../../services/contactService'
import { useChat } from '../../context/ChatContext'
import {
  Search,
  MessageSquare,
  Users,
  RefreshCw,
  Check,
  Share2,
  Sparkles,
  Link2,
} from 'lucide-react'

export function UserSearchDialog({ isOpen, onClose, onOpenSettings }) {
  const { startDirectChat } = useChat()

  const [activeTab, setActiveTab] = useState('search') // 'search' | 'contacts'
  const [searchTerm, setSearchTerm] = useState('')
  const [results, setResults] = useState([])
  const [isSearching, setIsSearching] = useState(false)
  const [error, setError] = useState(null)
  const [isStartingChat, setIsStartingChat] = useState(null)

  // Google Contacts State
  const [googleStatus, setGoogleStatus] = useState({ connected: false, isLoading: true })
  const [contacts, setContacts] = useState([])
  const [contactSearch, setContactSearch] = useState('')
  const [isLoadingContacts, setIsLoadingContacts] = useState(false)
  const [isSyncing, setIsSyncing] = useState(false)
  const [copiedEmail, setCopiedEmail] = useState(null)
  const [syncSuccessMsg, setSyncSuccessMsg] = useState(null)

  // Reset when dialog opens/closes
  useEffect(() => {
    if (!isOpen) {
      setSearchTerm('')
      setResults([])
      setError(null)
      setSyncSuccessMsg(null)
      return
    }

    // When dialog opens, check Google connection status
    fetchGoogleStatus()
  }, [isOpen])

  const fetchGoogleStatus = async () => {
    setGoogleStatus((prev) => ({ ...prev, isLoading: true }))
    try {
      const status = await contactService.getGoogleStatus()
      setGoogleStatus({ ...status, isLoading: false })
      if (status.connected) {
        loadContacts()
      }
    } catch {
      setGoogleStatus({ connected: false, isLoading: false })
    }
  }

  const loadContacts = async (query = '') => {
    setIsLoadingContacts(true)
    try {
      const res = await contactService.getContacts(query)
      setContacts(res.contacts || [])
    } catch {
      // Ignore or log error
    } finally {
      setIsLoadingContacts(false)
    }
  }

  // Debounced direct search
  useEffect(() => {
    if (activeTab !== 'search') return

    const trimmed = searchTerm.trim()
    if (!trimmed) {
      setResults([])
      setIsSearching(false)
      return
    }

    const timer = setTimeout(async () => {
      setIsSearching(true)
      setError(null)
      try {
        const users = await authService.searchUsers(trimmed)
        setResults(users || [])
      } catch {
        setError('Failed to search users.')
      } finally {
        setIsSearching(false)
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [searchTerm, activeTab])

  // Debounced contacts search
  useEffect(() => {
    if (activeTab !== 'contacts' || !googleStatus.connected) return

    const timer = setTimeout(() => {
      loadContacts(contactSearch.trim())
    }, 300)

    return () => clearTimeout(timer)
  }, [contactSearch, activeTab, googleStatus.connected])

  const handleSelectUser = async (targetUsername) => {
    setIsStartingChat(targetUsername)
    try {
      await startDirectChat(targetUsername)
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to open conversation.')
    } finally {
      setIsStartingChat(null)
    }
  }

  const handleSyncContacts = async () => {
    setIsSyncing(true)
    setError(null)
    setSyncSuccessMsg(null)
    try {
      const res = await contactService.syncGoogleContacts()
      setSyncSuccessMsg(res.message || 'Contacts synced successfully.')
      await loadContacts(contactSearch.trim())
    } catch (err) {
      setError(err.response?.data?.message || err.response?.data?.detail || 'Failed to sync Google contacts.')
    } finally {
      setIsSyncing(false)
    }
  }

  const handleCopyInvite = (contactEmail) => {
    const inviteLink = `${window.location.origin}/register?invited_by=${encodeURIComponent(contactEmail)}`
    navigator.clipboard?.writeText(inviteLink)
    setCopiedEmail(contactEmail)
    setTimeout(() => setCopiedEmail(null), 2500)
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Start New Conversation"
      description="Connect directly with teammates or discover colleagues from Google Contacts."
    >
      <div className="flex flex-col gap-4 mt-1">
        {/* Apple HIG Segmented Navigation Control */}
        <div className="flex p-1 bg-neutral-100 dark:bg-neutral-800 rounded-2xl">
          <button
            type="button"
            onClick={() => setActiveTab('search')}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-xl transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'search'
                ? 'bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-subtle'
                : 'text-neutral-500 hover:text-neutral-900 dark:hover:text-white'
            }`}
          >
            <Search className="w-3.5 h-3.5" /> Teammates
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('contacts')
              if (googleStatus.connected) loadContacts()
            }}
            className={`flex-1 py-1.5 text-xs font-semibold rounded-xl transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'contacts'
                ? 'bg-white dark:bg-neutral-700 text-neutral-900 dark:text-white shadow-subtle'
                : 'text-neutral-500 hover:text-neutral-900 dark:hover:text-white'
            }`}
          >
            <Users className="w-3.5 h-3.5" /> Google Contacts
            {googleStatus.connected && (
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 inline-block" />
            )}
          </button>
        </div>

        {error && <p className="text-xs text-red-500">{error}</p>}
        {syncSuccessMsg && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 p-2.5 rounded-xl">
            {syncSuccessMsg}
          </p>
        )}

        {/* Tab 1: Username / Platform Search */}
        {activeTab === 'search' && (
          <div className="flex flex-col gap-3">
            <Input
              placeholder="Search by username..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={Search}
              autoFocus
            />

            <div className="max-h-64 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-xl border border-neutral-100 dark:border-neutral-800">
              {isSearching ? (
                <div className="p-6 text-center text-xs text-neutral-400">
                  Searching users...
                </div>
              ) : results.length > 0 ? (
                results.map((u) => (
                  <div
                    key={u.id}
                    className="flex items-center justify-between p-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Avatar name={u.display_name || u.username} size="sm" />
                      <div className="min-w-0">
                        <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                          {u.display_name || u.username}
                        </p>
                        <p className="text-[11px] text-neutral-400 truncate">
                          @{u.username}
                        </p>
                      </div>
                    </div>

                    <Button
                      size="sm"
                      variant="primary"
                      onClick={() => handleSelectUser(u.username)}
                      isLoading={isStartingChat === u.username}
                      className="text-xs py-1 px-3"
                    >
                      <MessageSquare className="w-3.5 h-3.5 mr-1" /> Chat
                    </Button>
                  </div>
                ))
              ) : searchTerm.trim() ? (
                <div className="p-6 text-center text-xs text-neutral-400">
                  No registered teammate found matching "{searchTerm}"
                </div>
              ) : (
                <div className="p-6 text-center text-xs text-neutral-400">
                  Type at least 1 character to discover teammates.
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 2: Google Contacts */}
        {activeTab === 'contacts' && (
          <div className="flex flex-col gap-3">
            {!googleStatus.connected ? (
              <div className="p-6 text-center rounded-2xl bg-neutral-50 dark:bg-neutral-850/60 border border-black/[0.04] dark:border-white/[0.06] flex flex-col items-center gap-4">
                <div className="w-12 h-12 rounded-2xl bg-white dark:bg-neutral-800 flex items-center justify-center text-apple-blue shadow-subtle">
                  <Sparkles className="w-6 h-6" />
                </div>
                <div className="space-y-1.5 max-w-sm">
                  <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
                    Connect Google Contacts
                  </h3>
                  <p className="text-xs text-neutral-500 dark:text-neutral-400 leading-relaxed">
                    We request read-only access to your Google Contacts to match email addresses with registered colleagues already on Alignment Radar. Unregistered contacts are discarded and never stored or exposed.
                  </p>
                </div>
                <GoogleButton
                  label="Connect Google Contacts"
                  className="max-w-xs"
                  getAuthUrl={contactService.getGoogleContactsConnectUrl}
                  onError={(err) => setError(err)}
                />
              </div>
            ) : (
              <div className="flex flex-col gap-3">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1">
                    <Input
                      placeholder="Filter contacts by name or email..."
                      value={contactSearch}
                      onChange={(e) => setContactSearch(e.target.value)}
                      icon={Search}
                      autoFocus
                    />
                  </div>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={handleSyncContacts}
                    isLoading={isSyncing}
                    className="text-xs py-2 px-3 shrink-0"
                  >
                    <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${isSyncing ? 'animate-spin' : ''}`} />
                    Sync
                  </Button>
                </div>

                <div className="max-h-64 overflow-y-auto divide-y divide-neutral-100 dark:divide-neutral-800 rounded-xl border border-neutral-100 dark:border-neutral-800">
                  {isLoadingContacts ? (
                    <div className="p-6 text-center text-xs text-neutral-400">
                      Loading contacts...
                    </div>
                  ) : contacts.length > 0 ? (
                    contacts.map((c) => (
                      <div
                        key={c.id}
                        className="flex items-center justify-between p-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/50 transition-colors"
                      >
                        <div className="flex items-center gap-2.5 min-w-0 pr-2">
                          <Avatar name={c.contact_name || c.contact_email} size="sm" />
                          <div className="min-w-0">
                            <div className="flex items-center gap-1.5">
                              <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 truncate">
                                {c.contact_name || c.contact_email}
                              </p>
                              {c.is_registered && (
                                <span className="px-1.5 py-0.5 text-[9px] font-semibold bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600 dark:text-emerald-400 rounded-full border border-emerald-200 dark:border-emerald-800 tracking-wide uppercase shrink-0">
                                  On Radar
                                </span>
                              )}
                            </div>
                            <p className="text-[11px] text-neutral-400 truncate">
                              {c.contact_email}
                              {c.registered_username && ` • @${c.registered_username}`}
                            </p>
                          </div>
                        </div>

                        {c.is_registered ? (
                          <Button
                            size="sm"
                            variant="primary"
                            onClick={() => handleSelectUser(c.registered_username)}
                            isLoading={isStartingChat === c.registered_username}
                            className="text-xs py-1 px-3 shrink-0"
                          >
                            <MessageSquare className="w-3.5 h-3.5 mr-1" /> Chat
                          </Button>
                        ) : (
                          <Button
                            size="sm"
                            variant="ghost"
                            onClick={() => handleCopyInvite(c.contact_email)}
                            className="text-xs py-1 px-2.5 shrink-0 text-neutral-500 hover:text-neutral-900 dark:hover:text-white"
                          >
                            {copiedEmail === c.contact_email ? (
                              <>
                                <Check className="w-3.5 h-3.5 mr-1 text-emerald-500" /> Copied
                              </>
                            ) : (
                              <>
                                <Share2 className="w-3.5 h-3.5 mr-1" /> Invite
                              </>
                            )}
                          </Button>
                        )}
                      </div>
                    ))
                  ) : (
                    <div className="p-6 text-center text-xs text-neutral-400">
                      No contacts found. Click "Sync" above to import your Google address book.
                    </div>
                  )}
                </div>

                <div className="flex items-center justify-between text-[11px] text-neutral-400 px-1 pt-1">
                  <span>Only registered teammates are shown.</span>
                  {onOpenSettings && (
                    <button
                      type="button"
                      onClick={() => {
                        onClose()
                        onOpenSettings()
                      }}
                      className="text-apple-blue hover:underline"
                    >
                      Manage Integrations
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </Modal>
  )
}
