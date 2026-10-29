import React, { useState, useEffect, useCallback } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { Avatar } from '../ui/Avatar'
import { Badge } from '../ui/Badge'
import { groupService } from '../../services/groupService'
import { useAuth } from '../../context/AuthContext'
import { useChat } from '../../context/ChatContext'
import { Link as LinkIcon, Copy, Check, Shield, Share2, UserMinus, LogOut, AlertTriangle, Camera, Trash2 } from 'lucide-react'
import { formatFullDateTime } from '../../utils/date'

export function GroupDetails({ groupId, isOpen, onClose }) {
  const { sendMessage, refreshConversations, selectConversation, onlineUserIds = new Set() } = useChat()
  const { user } = useAuth()

  const [group, setGroup] = useState(null)
  const [members, setMembers] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  // Invitation creation state
  const [isCreatingInvite, setIsCreatingInvite] = useState(false)
  const [expiresInDays, setExpiresInDays] = useState(7)
  const [maxUses, setMaxUses] = useState('')
  const [generatedInvite, setGeneratedInvite] = useState(null)
  const [copied, setCopied] = useState(false)
  const [isInviteSubmitting, setIsInviteSubmitting] = useState(false)
  const [inviteError, setInviteError] = useState(null)
  const [sharedInChat, setSharedInChat] = useState(false)

  // Member management state
  const [removingMemberId, setRemovingMemberId] = useState(null)
  const [promotingMemberId, setPromotingMemberId] = useState(null)
  const [confirmRemoveMember, setConfirmRemoveMember] = useState(null)
  const [isLeaving, setIsLeaving] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)

  // Group photo state
  const [isUploadingAvatar, setIsUploadingAvatar] = useState(false)
  const [isRemovingAvatar, setIsRemovingAvatar] = useState(false)
  const [avatarError, setAvatarError] = useState(null)
  const [confirmRemoveAvatar, setConfirmRemoveAvatar] = useState(false)

  const loadGroup = useCallback(async () => {
    if (!groupId) return
    setIsLoading(true)
    setError(null)
    try {
      const [groupData, memberData] = await Promise.all([
        groupService.getGroup(groupId),
        groupService.getMembers(groupId),
      ])
      setGroup(groupData)
      setMembers(memberData || [])
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load group details.')
    } finally {
      setIsLoading(false)
    }
  }, [groupId])

  useEffect(() => {
    if (!isOpen || !groupId) return
    loadGroup()
  }, [isOpen, groupId, loadGroup])

  // Determine current user's role in this group
  const currentUserMember = members.find((m) => m.user_id === user?.id)
  const isAdmin = currentUserMember?.role === 'admin'

  const handleAvatarFileChange = async (e) => {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setAvatarError(null)
    setIsUploadingAvatar(true)
    try {
      const updated = await groupService.uploadGroupAvatar(groupId, file)
      setGroup((prev) => ({ ...prev, avatar_url: updated.avatar_url }))
      refreshConversations()
    } catch (err) {
      setAvatarError(err.response?.data?.detail || err.response?.data?.message || 'Failed to update group photo.')
    } finally {
      setIsUploadingAvatar(false)
    }
  }

  const handleRemoveAvatar = async () => {
    setAvatarError(null)
    setIsRemovingAvatar(true)
    try {
      const updated = await groupService.removeGroupAvatar(groupId)
      setGroup((prev) => ({ ...prev, avatar_url: updated.avatar_url }))
      refreshConversations()
    } catch (err) {
      setAvatarError(err.response?.data?.detail || err.response?.data?.message || 'Failed to remove group photo.')
    } finally {
      setIsRemovingAvatar(false)
      setConfirmRemoveAvatar(false)
    }
  }

  const handleCreateInvitation = async (e) => {
    e.preventDefault()
    setIsInviteSubmitting(true)
    setInviteError(null)
    setSharedInChat(false)

    try {
      const invite = await groupService.createInvitation(groupId, {
        maxUses: maxUses ? parseInt(maxUses, 10) : null,
        expiresInDays: parseInt(expiresInDays, 10) || 7,
      })
      const fullUrl = `${window.location.origin}/invitations/${invite.token}`
      setGeneratedInvite({ ...invite, fullUrl })
    } catch (err) {
      setInviteError(err.response?.data?.detail || 'Failed to generate invitation link.')
    } finally {
      setIsInviteSubmitting(false)
    }
  }

  const handleCopyLink = () => {
    if (generatedInvite?.fullUrl) {
      navigator.clipboard.writeText(generatedInvite.fullUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleShareInviteInChat = () => {
    if (!generatedInvite?.fullUrl) return
    sendMessage(
      `Join our group "${group?.title}": ${generatedInvite.fullUrl}`,
      'link_share',
      {
        url: generatedInvite.fullUrl,
        title: `Join ${group?.title}`,
        source: 'Group Invitation',
      }
    )
    setSharedInChat(true)
    setTimeout(() => setSharedInChat(false), 3000)
  }

  const handleRemoveMember = async (memberId, memberUserId) => {
    setRemovingMemberId(memberUserId)
    try {
      await groupService.removeMember(groupId, memberUserId)
      setMembers((prev) => prev.filter((m) => m.user_id !== memberUserId))
      await refreshConversations()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to remove member.')
    } finally {
      setRemovingMemberId(null)
    }
  }

  const handlePromoteMember = async (memberUserId) => {
    setPromotingMemberId(memberUserId)
    try {
      await groupService.promoteMember(groupId, memberUserId)
      setMembers((prev) =>
        prev.map((m) => (m.user_id === memberUserId ? { ...m, role: 'admin' } : m))
      )
      await refreshConversations()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to promote member to admin.')
    } finally {
      setPromotingMemberId(null)
    }
  }

  const handleLeaveGroup = async () => {
    setIsLeaving(true)
    try {
      await groupService.leaveGroup(groupId)
      await refreshConversations()
      selectConversation(null)
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to leave group.')
      setIsLeaving(false)
      setConfirmLeave(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={group?.title || 'Group Details'}
      description="View members and manage group settings."
      maxWidth="max-w-lg"
    >
      {isLoading ? (
        <div className="py-8 flex flex-col items-center justify-center">
          <div className="w-8 h-8 rounded-full border-2 border-apple-blue border-t-transparent animate-spin mb-2" />
          <p className="text-xs text-neutral-400">Loading group info...</p>
        </div>
      ) : error ? (
        <div className="p-3 text-xs bg-red-50 text-red-600 rounded-xl my-2">
          {error}
        </div>
      ) : (
        <div className="flex flex-col gap-5 max-h-[75vh] overflow-y-auto pr-1">
          {/* Group photo */}
          <div className="flex flex-col items-center gap-2 pt-1">
            {isAdmin ? (
              <label
                className="relative group/avatar rounded-full cursor-pointer"
                title="Change group photo"
                data-testid="change-group-avatar-label"
              >
                <Avatar name={group?.title} avatarUrl={group?.avatar_url} isGroup size="lg" />
                <span className="absolute inset-0 rounded-full bg-black/0 group-hover/avatar:bg-black/40 transition-colors flex items-center justify-center">
                  <Camera className="w-4 h-4 text-white opacity-0 group-hover/avatar:opacity-100 transition-opacity" />
                </span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  className="hidden"
                  onChange={handleAvatarFileChange}
                  disabled={isUploadingAvatar || isRemovingAvatar}
                  data-testid="group-avatar-file-input"
                />
              </label>
            ) : (
              <Avatar name={group?.title} avatarUrl={group?.avatar_url} isGroup size="lg" />
            )}

            {isAdmin && (
              <div className="flex items-center gap-3">
                {isUploadingAvatar && <span className="text-[11px] text-neutral-400">Uploading…</span>}
                {!isUploadingAvatar && group?.avatar_url && (
                  <button
                    type="button"
                    onClick={() => setConfirmRemoveAvatar(true)}
                    disabled={isRemovingAvatar}
                    className="flex items-center gap-1 text-[11px] font-medium text-red-600 hover:text-red-700 disabled:opacity-50"
                    data-testid="remove-group-avatar-btn"
                  >
                    <Trash2 className="w-3 h-3" />
                    {isRemovingAvatar ? 'Removing…' : 'Remove photo'}
                  </button>
                )}
              </div>
            )}

            {avatarError && (
              <p className="text-[11px] text-red-600 dark:text-red-400 text-center" data-testid="group-avatar-error">
                {avatarError}
              </p>
            )}

            {confirmRemoveAvatar && (
              <div className="w-full p-2.5 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/50 text-center">
                <p className="text-[11px] text-red-700 dark:text-red-300 mb-1.5">Remove the group photo?</p>
                <div className="flex items-center justify-center gap-2">
                  <Button size="sm" variant="ghost" className="text-xs py-1 px-2.5" onClick={() => setConfirmRemoveAvatar(false)}>
                    Cancel
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-xs py-1 px-2.5 text-red-600 hover:bg-red-100 dark:hover:bg-red-900/40"
                    onClick={handleRemoveAvatar}
                    isLoading={isRemovingAvatar}
                    data-testid="confirm-remove-group-avatar-btn"
                  >
                    Remove
                  </Button>
                </div>
              </div>
            )}
          </div>

          {/* Members list */}
          <div>
            <div className="flex items-center justify-between mb-2.5">
              <span className="text-xs font-semibold text-neutral-600 dark:text-neutral-400 uppercase tracking-wider">
                Members ({members.length})
              </span>
            </div>

            <div className="divide-y divide-neutral-100 dark:divide-neutral-800 rounded-2xl border border-neutral-100 dark:border-neutral-800 overflow-hidden">
              {members.map((member) => (
                <div
                  key={member.id}
                  className="flex items-center justify-between p-3 hover:bg-neutral-50 dark:hover:bg-neutral-800/40 transition-colors"
                >
                  <div className="flex items-center gap-2.5">
                    <div className="relative">
                      <Avatar name={member.display_name || member.username} avatarUrl={member.avatar_url} size="sm" />
                      {onlineUserIds.has(member.user_id) && (
                        <span
                          className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-500 ring-2 ring-white dark:ring-neutral-900"
                          data-testid={`member-online-${member.user_id}`}
                          title="Online"
                        />
                      )}
                    </div>
                    <div>
                      <p className="text-xs font-semibold text-neutral-900 dark:text-neutral-100">
                        {member.display_name || member.username}
                        {member.user_id === user?.id && (
                          <span className="ml-1 text-[10px] text-neutral-400">(you)</span>
                        )}
                      </p>
                      <p className="text-[11px] text-neutral-400">
                        @{member.username}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {member.role === 'admin' ? (
                      <Badge variant="blue" size="sm" className="gap-1">
                        <Shield className="w-2.5 h-2.5" /> Admin
                      </Badge>
                    ) : (
                      <Badge variant="neutral" size="sm">
                        Member
                      </Badge>
                    )}

                    {/* Make admin button for other non-admin members */}
                    {isAdmin && member.user_id !== user?.id && member.role !== 'admin' && (
                      <button
                        type="button"
                        onClick={() => handlePromoteMember(member.user_id)}
                        disabled={promotingMemberId === member.user_id}
                        className="px-2 py-0.5 rounded-lg text-[10px] font-medium bg-blue-50 dark:bg-blue-950/40 text-apple-blue hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors disabled:opacity-50"
                        title={`Make @${member.username} an admin`}
                        data-testid={`promote-admin-btn-${member.user_id}`}
                      >
                        {promotingMemberId === member.user_id ? 'Promoting...' : 'Make Admin'}
                      </button>
                    )}

                    {/* Admin can remove other members with confirmation */}
                    {isAdmin && member.user_id !== user?.id && (
                      <button
                        type="button"
                        onClick={() => setConfirmRemoveMember(member)}
                        disabled={removingMemberId === member.user_id}
                        className="p-1 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 text-neutral-400 hover:text-red-500 transition-colors disabled:opacity-50"
                        title={`Remove ${member.username}`}
                        data-testid={`remove-member-btn-${member.user_id}`}
                      >
                        <UserMinus className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Invitation Section - only for admins */}
          {isAdmin && (
            <div className="pt-4 border-t border-neutral-100 dark:border-neutral-800">
              <div className="flex items-center justify-between mb-3">
                <div>
                  <h4 className="text-xs font-semibold text-neutral-800 dark:text-neutral-200">
                    Invite Teammates
                  </h4>
                  <p className="text-[11px] text-neutral-400">
                    Create a secure join link for this group conversation.
                  </p>
                </div>

                {!isCreatingInvite && !generatedInvite && (
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setIsCreatingInvite(true)}
                  >
                    <LinkIcon className="w-3 h-3 mr-1" /> New Link
                  </Button>
                )}
              </div>

              {isCreatingInvite && (
                <form
                  onSubmit={handleCreateInvitation}
                  className="p-3.5 rounded-2xl bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200/80 dark:border-neutral-700/60 flex flex-col gap-3"
                >
                  {inviteError && (
                    <p className="text-xs text-red-500">{inviteError}</p>
                  )}

                  <div className="grid grid-cols-2 gap-3">
                    <Input
                      label="Expires in (days)"
                      type="number"
                      min={1}
                      max={90}
                      value={expiresInDays}
                      onChange={(e) => setExpiresInDays(e.target.value)}
                      required
                    />
                    <Input
                      label="Max Uses (optional)"
                      type="number"
                      min={1}
                      max={1000}
                      placeholder="Unlimited"
                      value={maxUses}
                      onChange={(e) => setMaxUses(e.target.value)}
                    />
                  </div>

                  <div className="flex justify-end gap-2 mt-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setIsCreatingInvite(false)}
                      disabled={isInviteSubmitting}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      type="submit"
                      variant="primary"
                      isLoading={isInviteSubmitting}
                    >
                      Generate Link
                    </Button>
                  </div>
                </form>
              )}

              {generatedInvite && (
                <div className="p-3.5 rounded-2xl bg-blue-50/70 dark:bg-blue-950/30 border border-blue-200/80 dark:border-blue-900/40">
                  <p className="text-[11px] font-semibold text-blue-900 dark:text-blue-200 mb-1.5">
                    Invitation Link Active
                  </p>

                  <div className="flex items-center gap-1.5 p-2 rounded-xl bg-white dark:bg-neutral-900 border border-blue-200 dark:border-blue-900/60 text-xs">
                    <span className="truncate flex-1 font-mono text-neutral-700 dark:text-neutral-300">
                      {generatedInvite.fullUrl}
                    </span>
                    <button
                      type="button"
                      onClick={handleCopyLink}
                      className="p-1 rounded-md hover:bg-neutral-100 dark:hover:bg-neutral-800 text-apple-blue font-medium flex items-center gap-1 shrink-0"
                      title="Copy to clipboard"
                    >
                      {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5" />}
                      <span>{copied ? 'Copied' : 'Copy'}</span>
                    </button>
                  </div>

                  <div className="flex items-center justify-between mt-2.5 text-[11px] text-neutral-500">
                    <span>Expires {formatFullDateTime(generatedInvite.expires_at)}</span>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={handleShareInviteInChat}
                      className="text-xs py-1 px-2.5 gap-1"
                    >
                      {sharedInChat ? (
                        <>
                          <Check className="w-3 h-3 text-emerald-600" />
                          <span>Shared in Chat</span>
                        </>
                      ) : (
                        <>
                          <Share2 className="w-3 h-3" />
                          <span>Share in Chat</span>
                        </>
                      )}
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Leave Group Section - for non-admin members */}
          {!isAdmin && currentUserMember && (
            <div className="pt-4 border-t border-neutral-100 dark:border-neutral-800">
              {!confirmLeave ? (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => setConfirmLeave(true)}
                  className="text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 w-full justify-center gap-1.5"
                >
                  <LogOut className="w-3.5 h-3.5" />
                  Leave Group
                </Button>
              ) : (
                <div className="p-3.5 rounded-2xl bg-red-50 dark:bg-red-950/30 border border-red-200/80 dark:border-red-800/40 flex flex-col gap-3">
                  <div className="flex items-start gap-2">
                    <AlertTriangle className="w-4 h-4 text-red-500 shrink-0 mt-0.5" />
                    <p className="text-xs text-red-700 dark:text-red-300">
                      You will lose access to this group and its messages. This cannot be undone.
                    </p>
                  </div>
                  <div className="flex gap-2 justify-end">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setConfirmLeave(false)}
                      disabled={isLeaving}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      className="bg-red-500 hover:bg-red-600 text-white"
                      isLoading={isLeaving}
                      onClick={handleLeaveGroup}
                    >
                      Confirm Leave
                    </Button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {confirmRemoveMember && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Confirm remove member"
          data-testid="remove-member-confirm-dialog"
          className="p-4 mt-3 rounded-2xl bg-amber-50 dark:bg-amber-950/40 border border-amber-300 dark:border-amber-800/60"
        >
          <div className="flex items-start gap-2 mb-2">
            <AlertTriangle className="w-4 h-4 text-amber-600 dark:text-amber-400 shrink-0 mt-0.5" />
            <div className="text-xs">
              <span className="font-semibold text-amber-900 dark:text-amber-200">
                Remove @{confirmRemoveMember.username} from group?
              </span>
              <p className="text-amber-800 dark:text-amber-300 mt-1">
                They will immediately lose access to group messages and attachments.
              </p>
            </div>
          </div>
          <div className="flex justify-end gap-2 mt-3">
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setConfirmRemoveMember(null)}
              disabled={removingMemberId === confirmRemoveMember.user_id}
            >
              Cancel
            </Button>
            <Button
              size="sm"
              variant="primary"
              className="bg-red-500 hover:bg-red-600 text-white"
              isLoading={removingMemberId === confirmRemoveMember.user_id}
              onClick={async () => {
                await handleRemoveMember(confirmRemoveMember.id, confirmRemoveMember.user_id)
                setConfirmRemoveMember(null)
              }}
              data-testid="confirm-remove-btn"
            >
              Confirm Remove
            </Button>
          </div>
        </div>
      )}
    </Modal>
  )
}
