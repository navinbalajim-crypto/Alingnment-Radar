import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { conversationService } from '../services/conversationService'
import { groupService } from '../services/groupService'
import { aiService } from '../services/aiService'
import { socketService } from '../services/socketService'
import { voiceService } from '../services/voiceService'
import { generateClientId } from '../utils/helpers'
import { useAuth } from './AuthContext'

const ChatContext = createContext(null)

export function ChatProvider({ children }) {
  const { user, isAuthenticated } = useAuth()

  const [conversations, setConversations] = useState([])
  const [activeConversationId, setActiveConversationId] = useState(null)
  const [activeConversation, setActiveConversation] = useState(null)

  const [messages, setMessages] = useState([])
  const [hasMoreMessages, setHasMoreMessages] = useState(false)
  const [nextCursor, setNextCursor] = useState(null)
  const [isLoadingMessages, setIsLoadingMessages] = useState(false)

  const [aiFindings, setAiFindings] = useState([])
  const [aiRecommendations, setAiRecommendations] = useState([])
  const [activeEvidenceId, setActiveEvidenceId] = useState(null)
  const [notifications, setNotifications] = useState([])

  // Feature Two: Active reply-to message
  const [replyTo, setReplyTo] = useState(null)

  // Feature Three: Live Conversation Context Graph
  const [contextGraph, setContextGraph] = useState({ active_nodes: [], inconsistencies: [] })

  const [socketStatus, setSocketStatus] = useState(socketService.getStatus())
  const [errorMessage, setErrorMessage] = useState(null)

  // Real-time presence: who is online (for DMs) and live online-member counts (for groups)
  const [onlineUserIds, setOnlineUserIds] = useState(() => new Set())
  const [groupOnlineCounts, setGroupOnlineCounts] = useState({})
  // True only after the server's presence snapshot for the current connection arrives.
  const [presenceReady, setPresenceReady] = useState(false)

  // Presence learned on a previous connection is stale once that connection drops;
  // the server sends a fresh snapshot when the socket reconnects.
  useEffect(() => {
    if (socketStatus !== 'connected') {
      setPresenceReady(false)
      setOnlineUserIds(new Set())
      setGroupOnlineCounts({})
    }
  }, [socketStatus])

  // Track active conversation ID ref to avoid stale closures in socket handlers
  const activeConvIdRef = useRef(activeConversationId)
  useEffect(() => {
    activeConvIdRef.current = activeConversationId
  }, [activeConversationId])

  // Track socket status
  useEffect(() => {
    const unsubscribe = socketService.onStatusChange((status) => {
      setSocketStatus(status)
    })
    return () => unsubscribe()
  }, [])

  // Refresh conversation list
  const refreshConversations = useCallback(async () => {
    if (!isAuthenticated) return
    try {
      const data = await conversationService.listConversations()
      const convList = Array.isArray(data) ? data : []
      setConversations(convList)
      setActiveConversation((prev) => {
        if (!prev) return prev
        const match = convList.find((c) => c && c.id === prev.id)
        return match ? { ...prev, ...match } : prev
      })
    } catch (err) {
      console.error('Failed to load conversations:', err)
    }
  }, [isAuthenticated])

  useEffect(() => {
    if (isAuthenticated) {
      refreshConversations()
      const pendingMeetConvId = localStorage.getItem('ar_pending_meet_conversation_id')
      if (pendingMeetConvId) {
        localStorage.removeItem('ar_pending_meet_conversation_id')
        selectConversation(pendingMeetConvId)
      }
    } else {
      setConversations([])
      setActiveConversationId(null)
      setActiveConversation(null)
      setMessages([])
      setAiFindings([])
      setAiRecommendations([])
      setNotifications([])
    }
  }, [isAuthenticated, refreshConversations])

  // Load conversation details, history, and AI items
  const selectConversation = useCallback(
    async (convId) => {
      if (!convId) {
        setActiveConversationId(null)
        setActiveConversation(null)
        setMessages([])
        setAiFindings([])
        setAiRecommendations([])
        setReplyTo(null)
        setContextGraph({ active_nodes: [], inconsistencies: [] })
        return
      }

      const isSwitchingConversation = convId !== activeConversationId
      setActiveConversationId(convId)
      setReplyTo(null)
      setIsLoadingMessages(true)
      setErrorMessage(null)
      if (isSwitchingConversation) {
        // Otherwise the previous conversation's messages stay on screen (and the loading
        // spinner never shows, since that only appears when the list is empty) for as long
        // as this fetch takes -- showing the wrong conversation's history, not just stale data.
        setMessages([])
        setAiFindings([])
        setAiRecommendations([])
        setContextGraph({ active_nodes: [], inconsistencies: [] })
      }

      // Join socket room
      socketService.joinConversation(convId)

      // Find from conversations list
      const existing = (conversations || []).find((c) => c && c.id === convId)
      if (existing) {
        setActiveConversation(existing)
      }

      try {
        const [messagesRes, aiItemsRes, graphRes] = await Promise.all([
          conversationService.getMessages(convId, { limit: 50 }),
          aiService.getAiItems(convId),
          typeof conversationService.getContextGraph === 'function'
            ? conversationService.getContextGraph(convId).catch(() => ({ active_nodes: [], inconsistencies: [] }))
            : Promise.resolve({ active_nodes: [], inconsistencies: [] }),
        ])

        setMessages(messagesRes.messages || [])
        setHasMoreMessages(messagesRes.has_more || false)
        setNextCursor(messagesRes.next_cursor || null)

        setAiFindings(aiItemsRes.findings || [])
        setAiRecommendations(aiItemsRes.recommendations || [])
        setContextGraph(graphRes || { active_nodes: [], inconsistencies: [] })
      } catch (err) {
        console.error('Failed to load conversation history/AI items:', err)
        setErrorMessage('Failed to load conversation messages.')
      } finally {
        setIsLoadingMessages(false)
      }
    },
    [conversations, activeConversationId]
  )

  // Load older messages for pagination
  const loadMoreMessages = useCallback(async () => {
    if (!activeConversationId || !hasMoreMessages || !nextCursor || isLoadingMessages) return

    try {
      const res = await conversationService.getMessages(activeConversationId, {
        limit: 50,
        before: nextCursor,
      })

      setMessages((prev) => [...(res.messages || []), ...prev])
      setHasMoreMessages(res.has_more || false)
      setNextCursor(res.next_cursor || null)
    } catch (err) {
      console.error('Failed to load older messages:', err)
    }
  }, [activeConversationId, hasMoreMessages, nextCursor, isLoadingMessages])

  // Send a message or upload attachment
  const sendMessage = useCallback(
    async (content, messageType = 'text', msgMetadata = {}, stagedFile = null, quotedReply = null) => {
      if (!activeConversationId || (!content?.trim() && !stagedFile)) return

      const clientId = generateClientId()
      const targetReply = quotedReply || replyTo

      if (stagedFile) {
        try {
          const res = await conversationService.uploadAttachment(
            activeConversationId,
            stagedFile,
            content?.trim() || null,
            clientId,
            targetReply?.id || null
          )
          setReplyTo(null)
          return res
        } catch (err) {
          console.error('Failed to upload attachment:', err)
          setErrorMessage(err.response?.data?.detail || err.message || 'Failed to upload attachment.')
          throw err
        }
      }

      const optimisticMessage = {
        id: clientId, // temporary ID until confirmed
        conversation_id: activeConversationId,
        sender_id: user?.id,
        sender_username: user?.username,
        content: content.trim(),
        message_type: messageType,
        msg_metadata: msgMetadata,
        client_id: clientId,
        created_at: new Date().toISOString(),
        isOptimistic: true,
        reply_to_message_id: targetReply ? targetReply.id : null,
        reply_to: targetReply
          ? {
              id: targetReply.id,
              sender_id: targetReply.sender_id,
              sender_username: targetReply.sender_username,
              content: targetReply.content,
              message_type: targetReply.message_type,
              is_deleted_for_everyone: Boolean(targetReply.is_deleted_for_everyone),
              has_attachment: Boolean(targetReply.attachments && targetReply.attachments.length > 0),
            }
          : null,
      }

      // Add optimistically to message stream
      setMessages((prev) => [...prev, optimisticMessage])
      setReplyTo(null)

      try {
        socketService.sendMessage({
          conversationId: activeConversationId,
          content: content.trim(),
          messageType,
          msgMetadata,
          clientId,
          replyToMessageId: targetReply ? targetReply.id : null,
        })
      } catch (err) {
        console.error('Failed to send message via socket:', err)
        setMessages((prev) =>
          prev.map((msg) =>
            msg.client_id === clientId ? { ...msg, isFailed: true } : msg
          )
        )
        setErrorMessage(err.message || 'Failed to send message.')
      }
    },
    [activeConversationId, user, replyTo]
  )

  // Delete message (Delete for me or Delete for everyone)
  const deleteMessage = useCallback(
    async (messageId, deleteType = 'me') => {
      if (!activeConversationId || !messageId) return
      try {
        await conversationService.deleteMessage(activeConversationId, messageId, deleteType)
        if (deleteType === 'me') {
          setMessages((prev) => prev.filter((m) => m.id !== messageId))
        } else if (deleteType === 'everyone') {
          setMessages((prev) =>
            prev.map((m) =>
              m.id === messageId
                ? {
                    ...m,
                    is_deleted_for_everyone: true,
                    content: 'This message was deleted.',
                    attachments: [],
                  }
                : m
            )
          )
        }
      } catch (err) {
        console.error('Failed to delete message:', err)
        setErrorMessage(err.response?.data?.detail || 'Failed to delete message.')
        throw err
      }
    },
    [activeConversationId]
  )

  // Share recommendation in chat
  const shareRecommendation = useCallback(
    async (recommendationId) => {
      if (!activeConversationId) return
      try {
        const sharedMsg = await aiService.shareRecommendation(
          activeConversationId,
          recommendationId
        )
        // Mark recommendation as shared in local state
        setAiRecommendations((prev) =>
          prev.map((rec) =>
            rec.id === recommendationId ? { ...rec, is_shared_in_chat: true } : rec
          )
        )
        return sharedMsg
      } catch (err) {
        console.error('Failed to share recommendation:', err)
        throw err
      }
    },
    [activeConversationId]
  )

  // Explicitly request recommendations
  const requestRecommendations = useCallback(
    async (optionsOrConvId = {}, maybeOptions = {}) => {
      let convId = activeConversationId
      let opts = {}

      if (typeof optionsOrConvId === 'string') {
        convId = optionsOrConvId
        opts = maybeOptions || {}
      } else if (optionsOrConvId && typeof optionsOrConvId === 'object') {
        opts = optionsOrConvId
        if (opts.conversationId) convId = opts.conversationId
      }

      if (!convId) return []
      try {
        const newRecs = await aiService.requestRecommendations(convId, opts)
        if (newRecs && newRecs.length > 0) {
          setAiRecommendations((prev) => {
            const seen = new Set(prev.map((r) => r.id))
            const filtered = newRecs.filter((r) => !seen.has(r.id))
            return [...prev, ...filtered]
          })
        }
        return newRecs
      } catch (err) {
        console.error('Failed to request recommendations:', err)
        throw err
      }
    },
    [activeConversationId]
  )

  // Explicitly trigger alignment analysis
  const triggerAlignment = useCallback(async () => {
    if (!activeConversationId) return null
    try {
      const res = await aiService.triggerAlignment(activeConversationId)
      const findings = Array.isArray(res) ? res : (res && res.mismatch_detected ? [res] : [])
      if (findings.length > 0) {
        setAiFindings((prev) => {
          const existingIds = new Set(prev.map((f) => f.id))
          const toAdd = findings.filter((f) => f && !existingIds.has(f.id))
          return toAdd.length > 0 ? [...prev, ...toAdd] : prev
        })
      }
      return res
    } catch (err) {
      console.error('Failed to trigger alignment analysis:', err)
      throw err
    }
  }, [activeConversationId])


  // Receiver asks the message author to clarify (posts a linked request into the chat)
  const requestClarification = useCallback(
    async (findingId, conversationId = null) => {
      const finding = aiFindings.find((f) => f.id === findingId)
      const convId = conversationId || activeConversationId || finding?.conversation_id
      if (!convId) return null
      const updated = await aiService.requestClarification(convId, findingId)
      setAiFindings((prev) => prev.map((f) => (f.id === findingId ? updated : f)))
      return updated
    },
    [activeConversationId, aiFindings]
  )

  // Confirm alignment resolution
  const confirmAlignment = useCallback(
    async (findingId, comment = null, conversationId = null) => {
      const finding = aiFindings.find((f) => f.id === findingId)
      const convId = conversationId || activeConversationId || finding?.conversation_id
      if (!convId) return null
      try {
        const updated = await aiService.confirmAlignment(convId, findingId, { comment })
        setAiFindings((prev) =>
          prev.map((f) => (f.id === findingId ? updated : f))
        )
        return updated
      } catch (err) {
        console.error('Failed to confirm alignment:', err)
        throw err
      }
    },
    [activeConversationId, aiFindings]
  )

  // Explicitly resolve alignment
  const resolveAlignment = useCallback(
    async (findingId, evidence = null, conversationId = null) => {
      const finding = aiFindings.find((f) => f.id === findingId)
      const convId = conversationId || activeConversationId || finding?.conversation_id
      if (!convId) return null
      try {
        const updated = await aiService.resolveAlignment(convId, findingId, { evidence })
        setAiFindings((prev) =>
          prev.map((f) => (f.id === findingId ? updated : f))
        )
        return updated
      } catch (err) {
        console.error('Failed to resolve alignment:', err)
        throw err
      }
    },
    [activeConversationId, aiFindings]
  )

  // Dismiss alignment finding
  const dismissAlignment = useCallback(
    async (findingId, reason = null, conversationId = null) => {
      const finding = aiFindings.find((f) => f.id === findingId)
      const convId = conversationId || activeConversationId || finding?.conversation_id
      if (!convId) return null
      try {
        await aiService.dismissAlignment(convId, findingId, { reason })
        setAiFindings((prev) => prev.filter((f) => f.id !== findingId))
      } catch (err) {
        console.error('Failed to dismiss alignment:', err)
        throw err
      }
    },
    [activeConversationId, aiFindings]
  )

  // Dismiss recommendation item
  const dismissRecommendation = useCallback(
    async (recommendationId, reason = null, conversationId = null) => {
      const rec = aiRecommendations.find((r) => r.id === recommendationId)
      const convId = conversationId || activeConversationId || rec?.conversation_id
      if (!convId) return null
      try {
        await aiService.dismissRecommendation(convId, recommendationId, { reason })
        setAiRecommendations((prev) => prev.filter((r) => r.id !== recommendationId))
      } catch (err) {
        console.error('Failed to dismiss recommendation:', err)
        throw err
      }
    },
    [activeConversationId, aiRecommendations]
  )

  // Start direct conversation with a username
  const startDirectChat = useCallback(
    async (targetUsername) => {
      try {
        const convSummary = await conversationService.getDirectConversation(targetUsername)
        await refreshConversations()
        selectConversation(convSummary.id)
        return convSummary
      } catch (err) {
        console.error('Failed to start direct conversation:', err)
        throw err
      }
    },
    [refreshConversations, selectConversation]
  )

  // Create a new group
  const createGroup = useCallback(
    async (title, initialMemberUsernames = []) => {
      try {
        const groupDetail = await groupService.createGroup(title, initialMemberUsernames)
        await refreshConversations()
        selectConversation(groupDetail.id)
        return groupDetail
      } catch (err) {
        console.error('Failed to create group:', err)
        throw err
      }
    },
    [refreshConversations, selectConversation]
  )

  // Highlight supporting evidence message
  const highlightEvidence = useCallback((messageId) => {
    setActiveEvidenceId(messageId)
    // Clear highlight after 2.5 seconds
    setTimeout(() => {
      setActiveEvidenceId((curr) => (curr === messageId ? null : curr))
    }, 2500)
  }, [])

  // Socket.IO event subscribers
  useEffect(() => {
    const handleMessageAck = (ackData) => {
      setMessages((prev) =>
        prev.map((msg) => {
          if (msg.client_id && msg.client_id === ackData.client_id) {
            return {
              ...msg,
              id: ackData.message_id,
              created_at: ackData.created_at,
              isOptimistic: false,
              isFailed: false,
            }
          }
          return msg
        })
      )
    }

    const handleMessageNew = (payload) => {
      const newMsg = payload.message
      if (!newMsg) return

      // Only append if it belongs to active conversation
      if (newMsg.conversation_id === activeConvIdRef.current) {
        setMessages((prev) => {
          // If already rendered via client_id or id, replace/update
          const existingIndex = prev.findIndex(
            (m) => (m.client_id && m.client_id === newMsg.client_id) || m.id === newMsg.id
          )
          if (existingIndex >= 0) {
            const updated = [...prev]
            updated[existingIndex] = { ...newMsg, isOptimistic: false }
            return updated
          }
          return [...prev, newMsg]
        })
      }

      // Update last_message in conversations list
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id === newMsg.conversation_id) {
            return {
              ...c,
              last_message: newMsg,
              updated_at: newMsg.created_at,
            }
          }
          return c
        })
      )
    }

    const handleMessageError = (errPayload) => {
      console.warn('Socket message error received:', errPayload)
      if (errPayload.client_id) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.client_id === errPayload.client_id
              ? { ...msg, isFailed: true, errorMessage: errPayload.message }
              : msg
          )
        )
      }
      setErrorMessage(errPayload.message || 'An error occurred with real-time messaging.')
    }

    const handleAiAlignment = (payload) => {
      const findings = payload.findings || (payload.finding ? [payload.finding] : [])
      if (!findings.length) return
      setAiFindings((prev) => {
        const existingIds = new Set(prev.map((f) => f.id))
        const toAdd = findings.filter(
          (f) => f && f.conversation_id === activeConvIdRef.current && !existingIds.has(f.id)
        )
        return toAdd.length > 0 ? [...prev, ...toAdd] : prev
      })
    }


    const handleAiAlignmentUpdate = (payload) => {
      const finding = payload.finding
      if (!finding) return
      if (finding.conversation_id === activeConvIdRef.current) {
        setAiFindings((prev) => {
          if (finding.status === 'dismissed') {
            return prev.filter((f) => f.id !== finding.id)
          }
          const exists = prev.some((f) => f.id === finding.id)
          if (exists) {
            return prev.map((f) => (f.id === finding.id ? finding : f))
          }
          return [...prev, finding]
        })
      }
    }

    const handleAiRecommendation = (payload) => {
      const recommendation = payload.recommendation
      if (!recommendation) return
      if (recommendation.conversation_id === activeConvIdRef.current) {
        setAiRecommendations((prev) => {
          if (prev.some((r) => r.id === recommendation.id)) return prev
          return [...prev, recommendation]
        })
      }
    }

    const handleAiRecommendationDismiss = (payload) => {
      const recId = payload.recommendation_id
      if (!recId) return
      setAiRecommendations((prev) => prev.filter((r) => r.id !== recId))
    }

    const handleGroupMemberJoined = (payload) => {
      // Refresh conversations list to update member count
      refreshConversations()
      // If viewing this group, also refresh active conversation details
      if (payload.group_id === activeConvIdRef.current) {
        refreshConversations()
      }
    }

    const handleGroupMemberLeft = (payload) => {
      // Refresh conversations list
      refreshConversations()
    }

    const handleMessageDeleted = (payload) => {
      if (!payload) return
      const { conversation_id, message_id, delete_type } = payload
      if (delete_type === 'everyone' && conversation_id === activeConvIdRef.current) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === message_id
              ? {
                  ...msg,
                  is_deleted_for_everyone: true,
                  content: 'This message was deleted.',
                  attachments: [],
                }
              : msg
          )
        )
      }
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id === conversation_id && c.last_message && c.last_message.id === message_id) {
            return {
              ...c,
              last_message: {
                ...c.last_message,
                is_deleted_for_everyone: true,
                content: 'This message was deleted.',
                attachments: [],
              },
            }
          }
          return c
        })
      )
    }

    const handleGroupMemberRemoved = (payload) => {
      if (!payload) return
      if (payload.user_id === user?.id && payload.group_id === activeConvIdRef.current) {
        setActiveConversationId(null)
        setActiveConversation(null)
        setMessages([])
      }
      refreshConversations()
    }

    const handleGroupRoleUpdated = () => {
      refreshConversations()
    }

    // Patches the sidebar entry and (if currently open) the header directly, instead of a
    // full refetch, so the photo change appears immediately for every connected member.
    const handleGroupAvatarUpdated = (payload) => {
      if (!payload || !payload.group_id) return
      const { group_id, avatar_url } = payload
      setConversations((prev) => prev.map((c) => (c && c.id === group_id ? { ...c, avatar_url } : c)))
      setActiveConversation((prev) => (prev && prev.id === group_id ? { ...prev, avatar_url } : prev))
    }

    const handleAiContextUpdate = (payload) => {
      if (!payload) return
      if (payload.conversation_id === activeConvIdRef.current) {
        setContextGraph({
          active_nodes: payload.active_nodes || [],
          inconsistencies: payload.inconsistencies || [],
          total_active_nodes: payload.total_active_nodes || 0,
          total_inconsistencies: payload.total_inconsistencies || 0,
        })
      }
    }

    const handleReminderNotify = (payload) => {
      if (!payload) return
      setNotifications((prev) => [
        {
          id: payload.reminder_id || generateClientId(),
          type: 'reminder',
          title: payload.title || 'Task Reminder',
          description: payload.due_text || payload.description || '',
          timestamp: new Date().toISOString(),
        },
        ...prev,
      ])
    }

    const handleVoiceTranscriptUpdated = (payload) => {
      if (!payload) return
      const { conversation_id, message_id, transcript } = payload
      if (conversation_id === activeConvIdRef.current) {
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === message_id
              ? {
                  ...msg,
                  voice_transcript: transcript,
                }
              : msg
          )
        )
      }
    }

    const handleVoiceTranslationUpdated = (payload) => {
      if (!payload) return
      const { conversation_id, message_id, target_language, translated_text, provider } = payload
      if (conversation_id === activeConvIdRef.current) {
        setMessages((prev) =>
          prev.map((msg) => {
            if (msg.id === message_id && msg.voice_transcript) {
              const prevTranslations = msg.voice_transcript.translations || {}
              return {
                ...msg,
                voice_transcript: {
                  ...msg.voice_transcript,
                  translations: {
                    ...prevTranslations,
                    [target_language]: {
                      text: translated_text,
                      provider,
                      translated_at: new Date().toISOString(),
                    },
                  },
                },
              }
            }
            return msg
          })
        )
      }
    }

    const handlePresenceSnapshot = (payload) => {
      if (!payload) return
      setOnlineUserIds(new Set(payload.online_user_ids || []))
      const counts = {}
      for (const g of payload.group_online_counts || []) {
        counts[g.conversation_id] = g.online_count
      }
      setGroupOnlineCounts(counts)
      setPresenceReady(true)
    }

    const handlePresenceUpdate = (payload) => {
      if (!payload || !payload.user_id) return
      setOnlineUserIds((prev) => {
        const next = new Set(prev)
        if (payload.is_online) next.add(payload.user_id)
        else next.delete(payload.user_id)
        return next
      })
    }

    const handlePresenceGroupUpdate = (payload) => {
      if (!payload || !payload.conversation_id) return
      setGroupOnlineCounts((prev) => ({ ...prev, [payload.conversation_id]: payload.online_count }))
    }

    socketService.on('message:ack', handleMessageAck)
    socketService.on('message:new', handleMessageNew)
    socketService.on('message:error', handleMessageError)
    socketService.on('message:deleted', handleMessageDeleted)
    socketService.on('ai:alignment', handleAiAlignment)
    socketService.on('ai:alignment_update', handleAiAlignmentUpdate)
    socketService.on('ai:recommendation', handleAiRecommendation)
    socketService.on('ai:recommendation_dismiss', handleAiRecommendationDismiss)
    socketService.on('ai:context_update', handleAiContextUpdate)
    socketService.on('group:member_joined', handleGroupMemberJoined)
    socketService.on('group:member_left', handleGroupMemberLeft)
    socketService.on('group:member_removed', handleGroupMemberRemoved)
    socketService.on('group:role_updated', handleGroupRoleUpdated)
    socketService.on('group:avatar_updated', handleGroupAvatarUpdated)
    socketService.on('reminder:notify', handleReminderNotify)
    socketService.on('voice:transcript_updated', handleVoiceTranscriptUpdated)
    socketService.on('voice:translation_updated', handleVoiceTranslationUpdated)
    socketService.on('presence:snapshot', handlePresenceSnapshot)
    socketService.on('presence:update', handlePresenceUpdate)
    socketService.on('presence:group_update', handlePresenceGroupUpdate)

    return () => {
      socketService.off('message:ack', handleMessageAck)
      socketService.off('message:new', handleMessageNew)
      socketService.off('message:error', handleMessageError)
      socketService.off('message:deleted', handleMessageDeleted)
      socketService.off('ai:alignment', handleAiAlignment)
      socketService.off('ai:alignment_update', handleAiAlignmentUpdate)
      socketService.off('ai:recommendation', handleAiRecommendation)
      socketService.off('ai:recommendation_dismiss', handleAiRecommendationDismiss)
      socketService.off('ai:context_update', handleAiContextUpdate)
      socketService.off('group:member_joined', handleGroupMemberJoined)
      socketService.off('group:member_left', handleGroupMemberLeft)
      socketService.off('group:member_removed', handleGroupMemberRemoved)
      socketService.off('group:role_updated', handleGroupRoleUpdated)
      socketService.off('group:avatar_updated', handleGroupAvatarUpdated)
      socketService.off('reminder:notify', handleReminderNotify)
      socketService.off('voice:transcript_updated', handleVoiceTranscriptUpdated)
      socketService.off('voice:translation_updated', handleVoiceTranslationUpdated)
      socketService.off('presence:snapshot', handlePresenceSnapshot)
      socketService.off('presence:update', handlePresenceUpdate)
      socketService.off('presence:group_update', handlePresenceGroupUpdate)
    }
  }, [refreshConversations, user])

  // Context graph action handlers
  const dismissInconsistency = useCallback(
    async (inconsistencyId) => {
      if (!activeConversationId || !inconsistencyId) return
      try {
        await conversationService.dismissInconsistency(activeConversationId, inconsistencyId)
        setContextGraph((prev) => ({
          ...prev,
          inconsistencies: (prev.inconsistencies || []).filter((i) => i.id !== inconsistencyId),
        }))
      } catch (err) {
        console.error('Failed to dismiss inconsistency:', err)
      }
    },
    [activeConversationId]
  )

  const resolveInconsistency = useCallback(
    async (inconsistencyId, note = null) => {
      if (!activeConversationId || !inconsistencyId) return
      try {
        await conversationService.resolveInconsistency(activeConversationId, inconsistencyId, note)
        setContextGraph((prev) => ({
          ...prev,
          inconsistencies: (prev.inconsistencies || []).filter((i) => i.id !== inconsistencyId),
        }))
      } catch (err) {
        console.error('Failed to resolve inconsistency:', err)
      }
    },
    [activeConversationId]
  )

  const resolveContextNode = useCallback(
    async (nodeId, status = 'completed', note = null) => {
      if (!activeConversationId || !nodeId) return
      try {
        await conversationService.resolveNode(activeConversationId, nodeId, status, note)
        setContextGraph((prev) => ({
          ...prev,
          active_nodes: (prev.active_nodes || []).filter((n) => n.id !== nodeId),
        }))
      } catch (err) {
        console.error('Failed to resolve context node:', err)
      }
    },
    [activeConversationId]
  )

  const sendVoiceNote = useCallback(
    async (audioBlob, duration) => {
      if (!activeConversationId) return null
      const clientId = generateClientId()
      const replyToId = replyTo ? replyTo.id : null
      try {
        const result = await voiceService.uploadVoiceNote(
          activeConversationId,
          audioBlob,
          duration,
          clientId,
          replyToId
        )
        setReplyTo(null)
        if (result?.message) {
          const freshMsg = result.message
          setMessages((prev) => {
            const existingIndex = prev.findIndex(
              (m) =>
                (m.client_id && m.client_id === freshMsg.client_id) ||
                m.id === freshMsg.id
            )
            if (existingIndex >= 0) {
              const updated = [...prev]
              updated[existingIndex] = { ...freshMsg, isOptimistic: false }
              return updated
            }
            return [...prev, freshMsg]
          })
          setConversations((prev) =>
            prev.map((c) =>
              c.id === freshMsg.conversation_id
                ? { ...c, last_message: freshMsg, updated_at: freshMsg.created_at }
                : c
            )
          )
        }
        return result
      } catch (err) {
        console.error('Failed to send voice note:', err)
        setErrorMessage(err.response?.data?.message || err.message || 'Failed to send voice note.')
        throw err
      }
    },
    [activeConversationId, replyTo]
  )

  return (
    <ChatContext.Provider
      value={{
        conversations,
        activeConversationId,
        activeConversation,
        messages,
        hasMoreMessages,
        isLoadingMessages,
        aiFindings,
        aiRecommendations,
        activeEvidenceId,
        notifications,
        setNotifications,
        socketStatus,
        errorMessage,
        setErrorMessage,
        onlineUserIds,
        groupOnlineCounts,
        presenceReady,
        replyTo,
        setReplyTo,
        contextGraph,
        dismissInconsistency,
        resolveInconsistency,
        resolveContextNode,
        selectConversation,
        loadMoreMessages,
        sendMessage,
        sendVoiceNote,
        deleteMessage,
        shareRecommendation,
        confirmAlignment,
        requestClarification,
        resolveAlignment,
        dismissAlignment,
        dismissRecommendation,
        startDirectChat,
        createGroup,
        refreshConversations,
        highlightEvidence,
        requestRecommendations,
        triggerAlignment,
      }}
    >
      {children}
    </ChatContext.Provider>
  )
}

export function useChat() {
  const context = useContext(ChatContext)
  if (!context) {
    throw new Error('useChat must be used within a ChatProvider')
  }
  return context
}
