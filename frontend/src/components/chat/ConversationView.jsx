import React, { useRef } from 'react'
import { ConversationHeader } from '../layout/ConversationHeader'
import { MessageList } from './MessageList'
import { MessageComposer } from './MessageComposer'
import { useChat } from '../../context/ChatContext'
import { Compass, MessageSquarePlus, X } from 'lucide-react'

export function ConversationView({ onToggleSidebar }) {
  const {
    activeConversation,
    messages,
    isLoadingMessages,
    hasMoreMessages,
    loadMoreMessages,
    sendMessage,
    aiFindings,
    aiRecommendations,
    errorMessage,
    setErrorMessage,
    contextGraph,
    dismissInconsistency,
    resolveInconsistency,
    highlightEvidence,
  } = useChat()

  const composerRef = useRef(null)

  const handleApplyQuestion = (question) => {
    composerRef.current?.setText(question)
  }

  if (!activeConversation) {
    return (
      <main className="flex-1 h-full flex flex-col items-center justify-center p-8 bg-[#F9F9FB] dark:bg-neutral-950 text-center select-none">
        <div className="w-16 h-16 rounded-3xl bg-white dark:bg-neutral-900 border border-black/[0.06] dark:border-white/[0.08] shadow-apple flex items-center justify-center text-apple-blue mb-4">
          <Compass className="w-8 h-8" />
        </div>
        <h2 className="text-base font-semibold text-neutral-800 dark:text-neutral-200">
          Select a Conversation
        </h2>
        <p className="text-xs text-neutral-500 dark:text-neutral-400 mt-1 max-w-sm">
          Choose a direct chat or group from the sidebar, or start a new conversation to begin real-time messaging with AI alignment detection.
        </p>

        {onToggleSidebar && (
          <button
            type="button"
            onClick={onToggleSidebar}
            className="md:hidden mt-4 inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-apple-blue text-white text-xs font-medium shadow-subtle"
          >
            <MessageSquarePlus className="w-4 h-4" /> Open Conversations
          </button>
        )}
      </main>
    )
  }

  return (
    <main className="flex-1 h-full flex flex-col bg-[#F9F9FB] dark:bg-neutral-950 min-w-0 overflow-hidden">
      {/* Header */}
      <ConversationHeader
        conversation={activeConversation}
        onToggleSidebar={onToggleSidebar}
      />

      {/* Ephemeral Error Notification */}
      {errorMessage && (
        <div className="mx-4 mt-2 px-3.5 py-2 rounded-xl bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900/40 text-xs text-red-600 dark:text-red-300 flex items-center justify-between shadow-subtle shrink-0">
          <span>{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="p-1 text-red-400 hover:text-red-700"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* Scrollable Message History with Inline AI Items and Live Context Graph */}
      <MessageList
        conversationId={activeConversation.id}
        messages={messages}
        aiFindings={aiFindings}
        aiRecommendations={aiRecommendations}
        contextGraph={contextGraph}
        onDismissInconsistency={dismissInconsistency}
        onResolveInconsistency={resolveInconsistency}
        onHighlightEvidence={highlightEvidence}
        isLoading={isLoadingMessages}
        hasMore={hasMoreMessages}
        onLoadMore={loadMoreMessages}
        onApplyQuestion={handleApplyQuestion}
      />

      {/* Message Composer fixed at bottom */}
      <MessageComposer
        ref={composerRef}
        onSend={(content, file, reply) => sendMessage(content, file ? 'attachment' : 'text', {}, file, reply)}
      />
    </main>
  )
}
