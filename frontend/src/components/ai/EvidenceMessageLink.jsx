import React from 'react'
import { Hash } from 'lucide-react'
import { useChat } from '../../context/ChatContext'

export function EvidenceMessageLink({ messageId, index }) {
  const { highlightEvidence } = useChat()

  const handleClick = (e) => {
    e.preventDefault()
    // Scroll to the message element in the chat DOM
    const el = document.getElementById(`msg-${messageId}`)
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' })
      highlightEvidence(messageId)
    } else {
      // Still trigger highlight state
      highlightEvidence(messageId)
    }
  }

  // Display short label like "#Msg 1" or "#Msg 2"
  const label = index !== undefined ? `Message #${index + 1}` : `Msg ${String(messageId).slice(0, 6)}`

  return (
    <button
      type="button"
      onClick={handleClick}
      className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-md bg-amber-100/70 hover:bg-amber-200/80 dark:bg-amber-900/40 dark:hover:bg-amber-900/60 text-amber-900 dark:text-amber-200 transition-colors cursor-pointer border border-amber-300/50 dark:border-amber-700/50"
      title={`Click to scroll to message: ${messageId}`}
    >
      <Hash className="w-2.5 h-2.5" />
      <span>{label}</span>
    </button>
  )
}
