import React, { useState } from 'react'
import { Modal } from '../ui/Modal'
import { Input } from '../ui/Input'
import { Button } from '../ui/Button'
import { useChat } from '../../context/ChatContext'
import { Users, Plus } from 'lucide-react'

export function CreateGroupDialog({ isOpen, onClose }) {
  const { createGroup } = useChat()
  const [title, setTitle] = useState('')
  const [initialMembersInput, setInitialMembersInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!title.trim()) return

    setIsLoading(true)
    setError(null)

    // Parse comma- or space-separated usernames
    const memberUsernames = initialMembersInput
      .split(/[,\s]+/)
      .map((u) => u.replace(/^@/, '').trim())
      .filter(Boolean)

    try {
      await createGroup(title.trim(), memberUsernames)
      setTitle('')
      setInitialMembersInput('')
      onClose()
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to create group conversation.')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Create New Group"
      description="Start a collaborative conversation room for your team."
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 mt-2">
        {error && (
          <div className="p-3 text-xs bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-red-600 dark:text-red-300 rounded-xl">
            {error}
          </div>
        )}

        <Input
          label="Group Title"
          placeholder="e.g. Frontend Engineering, Product Roadmap"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          required
          disabled={isLoading}
          icon={Users}
          autoFocus
        />

        <Input
          label="Initial Members (optional)"
          placeholder="e.g. alex_chen, sarah_w (comma-separated)"
          value={initialMembersInput}
          onChange={(e) => setInitialMembersInput(e.target.value)}
          disabled={isLoading}
          helperText="Add registered usernames to invite right away, or generate an invitation link later."
        />

        <div className="flex justify-end gap-2 mt-4 pt-3 border-t border-neutral-100 dark:border-neutral-800">
          <Button
            type="button"
            variant="ghost"
            onClick={onClose}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button
            type="submit"
            variant="primary"
            disabled={!title.trim()}
            isLoading={isLoading}
          >
            <Plus className="w-4 h-4 mr-1" /> Create Group
          </Button>
        </div>
      </form>
    </Modal>
  )
}
