import { io } from 'socket.io-client'
import { getAccessToken } from './apiClient'

function getSocketUrl() {
  const envUrl = import.meta.env.VITE_SOCKET_URL
  if (typeof window !== 'undefined' && window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') {
    if (!envUrl || envUrl.includes('localhost') || envUrl.includes('127.0.0.1')) {
      return 'https://alingnment-radar.onrender.com'
    }
  }
  return envUrl || (typeof window !== 'undefined' ? window.location.origin : 'https://alingnment-radar.onrender.com')
}

const SOCKET_URL = getSocketUrl()

class SocketService {
  constructor() {
    this.socket = null
    this.currentConversationId = null
    this.statusListeners = new Set()
    this.status = 'disconnected' // 'disconnected' | 'connecting' | 'connected' | 'error'
  }

  getStatus() {
    return this.status
  }

  onStatusChange(listener) {
    this.statusListeners.add(listener)
    listener(this.status)
    return () => this.statusListeners.delete(listener)
  }

  _setStatus(newStatus) {
    this.status = newStatus
    this.statusListeners.forEach((listener) => {
      try {
        listener(newStatus)
      } catch (err) {
        console.error('Error in socket status listener:', err)
      }
    })
  }

  connect(explicitToken = null) {
    const token = explicitToken || getAccessToken()
    if (!token) {
      console.warn('Socket connect skipped: No access token available.')
      return
    }

    // Reuse a socket that is connected or still handshaking; tearing it down mid-handshake
    // drops listeners already registered on it and delays the first send.
    if (this.socket && (this.socket.connected || this.socket.active) && this.socketToken === token) {
      return
    }

    if (this.socket) {
      this.socket.disconnect()
    }

    this._setStatus('connecting')
    this.socketToken = token

    this.socket = io(SOCKET_URL, {
      path: '/socket.io',
      // Evaluated on every (re)connect so reconnects use the latest refreshed access token.
      auth: (cb) => cb({ token: `Bearer ${getAccessToken() || token}` }),
      transports: ['websocket', 'polling'],
      autoConnect: true,
      reconnection: true,
      reconnectionAttempts: 10,
      reconnectionDelay: 1000,
      reconnectionDelayMax: 5000,
      timeout: 20000,
    })

    this.socket.on('connect', () => {
      this._setStatus('connected')
      // If we were already in a conversation room before disconnect, re-join it
      if (this.currentConversationId) {
        this.joinConversation(this.currentConversationId)
      }
    })

    this.socket.on('connect_error', (err) => {
      console.warn('Socket connection error:', err.message)
      this._setStatus('error')
    })

    this.socket.on('disconnect', (reason) => {
      this._setStatus('disconnected')
    })
  }

  disconnect() {
    if (this.socket) {
      this.socket.disconnect()
      this.socket = null
    }
    this.currentConversationId = null
    this._setStatus('disconnected')
  }

  joinConversation(conversationId) {
    this.currentConversationId = conversationId
    if (this.socket && this.socket.connected && conversationId) {
      this.socket.emit('conversation:join', { conversation_id: conversationId })
    }
  }

  sendMessage({ conversationId, content, messageType = 'text', msgMetadata = {}, clientId, replyToMessageId = null }) {
    if (!this.socket || !this.socket.connected) {
      throw new Error('Real-time connection is not active. Please reconnect or check backend.')
    }
    const payload = {
      conversation_id: conversationId,
      content,
      message_type: messageType,
      msg_metadata: msgMetadata,
      client_id: clientId,
    }
    if (replyToMessageId) {
      payload.reply_to_message_id = replyToMessageId
    }
    this.socket.emit('message:send', payload)
  }

  on(eventName, callback) {
    if (!this.socket) {
      // Connect first if needed
      this.connect()
    }
    if (this.socket) {
      this.socket.on(eventName, callback)
    }
  }

  off(eventName, callback) {
    if (this.socket) {
      this.socket.off(eventName, callback)
    }
  }
}

export const socketService = new SocketService()
