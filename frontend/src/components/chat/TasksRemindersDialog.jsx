import React, { useState, useEffect, useCallback } from 'react'
import { Modal } from '../ui/Modal'
import { Button } from '../ui/Button'
import { Input } from '../ui/Input'
import { reminderService } from '../../services/reminderService'
import { useAuth } from '../../context/AuthContext'
import { useChat } from '../../context/ChatContext'
import {
  Bell,
  CheckCircle2,
  Clock,
  Calendar,
  Sparkles,
  Trash2,
  AlertCircle,
  User as UserIcon,
} from 'lucide-react'
import { formatFullDateTime } from '../../utils/date'

export function TasksRemindersDialog({ conversationId, isOpen, onClose }) {
  const { user } = useAuth()
  const { activeConversation } = useChat()

  const [reminders, setReminders] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  // Creation form state
  const [isCreating, setIsCreating] = useState(false)
  const [nlText, setNlText] = useState('')
  const [isExtracting, setIsExtracting] = useState(false)
  const [taskTitle, setTaskTitle] = useState('')
  const [dueDate, setDueDate] = useState('')
  const [dueTime, setDueTime] = useState('10:00')
  const [advanceMinutes, setAdvanceMinutes] = useState(30)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const loadReminders = useCallback(async () => {
    if (!conversationId) return
    setIsLoading(true)
    setError(null)
    try {
      const data = await reminderService.listReminders(conversationId)
      setReminders(Array.isArray(data) ? data : [])
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to load reminders.')
    } finally {
      setIsLoading(false)
    }
  }, [conversationId])

  useEffect(() => {
    if (isOpen && conversationId) {
      loadReminders()
    }
  }, [isOpen, conversationId, loadReminders])

  const handleExtractFromNl = async () => {
    if (!nlText.trim()) return
    setIsExtracting(true)
    setError(null)
    try {
      const res = await reminderService.extractTask(conversationId, nlText.trim())
      if (res.task_detected && res.task) {
        setTaskTitle(res.task.title || '')
        if (res.task.due_at) {
          const dt = new Date(res.task.due_at)
          const yyyy = dt.getFullYear()
          const mm = String(dt.getMonth() + 1).padStart(2, '0')
          const dd = String(dt.getDate()).padStart(2, '0')
          setDueDate(`${yyyy}-${mm}-${dd}`)
          const hh = String(dt.getHours()).padStart(2, '0')
          const min = String(dt.getMinutes()).padStart(2, '0')
          setDueTime(`${hh}:${min}`)
        }
      } else {
        setError('No deadline or task could be identified in the text. Please specify details below.')
      }
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to extract task.')
    } finally {
      setIsExtracting(false)
    }
  }

  const handleCreateReminder = async (e) => {
    e.preventDefault()
    if (!taskTitle.trim() || !dueDate) {
      setError('Please provide a task title and due date.')
      return
    }

    setIsSubmitting(true)
    setError(null)
    try {
      const dueIso = new Date(`${dueDate}T${dueTime || '10:00'}:00`).toISOString()
      const payload = {
        title: taskTitle.trim(),
        due_at: dueIso,
        advance_reminder_minutes: parseInt(advanceMinutes, 10) || 30,
        timezone: 'Asia/Kolkata',
      }
      const newRem = await reminderService.createReminder(conversationId, payload)
      setReminders((prev) => [newRem, ...prev])
      setIsCreating(false)
      setTaskTitle('')
      setDueDate('')
      setNlText('')
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to schedule reminder.')
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleToggleComplete = async (reminder) => {
    const nextStatus = reminder.status === 'completed' ? 'pending' : 'completed'
    try {
      const updated = await reminderService.updateReminder(reminder.id, { status: nextStatus })
      setReminders((prev) => prev.map((r) => (r.id === reminder.id ? updated : r)))
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to update reminder status.')
    }
  }

  const handleCancelReminder = async (reminderId) => {
    try {
      const updated = await reminderService.updateReminder(reminderId, { status: 'cancelled' })
      setReminders((prev) => prev.map((r) => (r.id === reminderId ? updated : r)))
    } catch (err) {
      setError(err.response?.data?.detail || 'Failed to cancel reminder.')
    }
  }

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Tasks & Reminders"
      description="Persistent conversation deadlines with advance and due-time notifications."
      maxWidth="max-w-lg"
    >
      <div className="space-y-4" data-testid="tasks-reminders-panel">
        {error && (
          <div className="p-3 text-xs bg-red-50 text-red-600 rounded-xl flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-neutral-800 dark:text-neutral-200">
            Active Reminders ({reminders.filter((r) => r.status === 'pending').length})
          </span>
          {!isCreating && (
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setIsCreating(true)}
              className="gap-1 text-xs"
              data-testid="create-reminder-btn"
            >
              <Bell className="w-3.5 h-3.5" />
              <span>New Reminder</span>
            </Button>
          )}
        </div>

        {/* Creation section */}
        {isCreating && (
          <form
            onSubmit={handleCreateReminder}
            className="p-4 rounded-2xl bg-neutral-50 dark:bg-neutral-800/50 border border-neutral-200 dark:border-neutral-700 space-y-3"
            data-testid="reminder-form"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-neutral-900 dark:text-neutral-100 flex items-center gap-1.5">
                <Sparkles className="w-3.5 h-3.5 text-apple-blue" />
                Schedule Task Reminder
              </span>
              <button
                type="button"
                onClick={() => setIsCreating(false)}
                className="text-xs text-neutral-400 hover:text-neutral-600"
              >
                Cancel
              </button>
            </div>

            {/* Natural language helper */}
            <div className="space-y-1">
              <label className="text-[11px] font-medium text-neutral-500">
                Natural Language Quick Extraction (Optional)
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="e.g., Tomorrow at 10 AM, submit the frontend"
                  value={nlText}
                  onChange={(e) => setNlText(e.target.value)}
                  className="flex-1 px-3 py-1.5 text-xs rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={handleExtractFromNl}
                  disabled={isExtracting || !nlText.trim()}
                  className="shrink-0 text-xs"
                >
                  {isExtracting ? 'Detecting...' : 'Extract'}
                </Button>
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-medium text-neutral-500">Task Title</label>
              <input
                type="text"
                placeholder="Submit frontend implementation"
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
                required
                className="w-full px-3 py-1.5 text-xs rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800"
                data-testid="reminder-title-input"
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[11px] font-medium text-neutral-500">Due Date</label>
                <input
                  type="date"
                  value={dueDate}
                  onChange={(e) => setDueDate(e.target.value)}
                  required
                  className="w-full px-3 py-1.5 text-xs rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800"
                  data-testid="reminder-date-input"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-medium text-neutral-500">Due Time</label>
                <input
                  type="time"
                  value={dueTime}
                  onChange={(e) => setDueTime(e.target.value)}
                  required
                  className="w-full px-3 py-1.5 text-xs rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800"
                  data-testid="reminder-time-input"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] font-medium text-neutral-500">
                Advance Notification (Minutes Before)
              </label>
              <select
                value={advanceMinutes}
                onChange={(e) => setAdvanceMinutes(e.target.value)}
                className="w-full px-3 py-1.5 text-xs rounded-xl border border-neutral-200 dark:border-neutral-700 bg-white dark:bg-neutral-800"
              >
                <option value={10}>10 minutes before</option>
                <option value={15}>15 minutes before</option>
                <option value={30}>30 minutes before (Default)</option>
                <option value={60}>1 hour before</option>
                <option value={120}>2 hours before</option>
                <option value={1440}>1 day before</option>
              </select>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-neutral-200/60 dark:border-neutral-700/60">
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setIsCreating(false)}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                size="sm"
                variant="primary"
                isLoading={isSubmitting}
                data-testid="confirm-save-reminder-btn"
              >
                Schedule Reminder
              </Button>
            </div>
          </form>
        )}

        {/* Reminders List */}
        {isLoading ? (
          <div className="py-8 flex flex-col items-center justify-center">
            <div className="w-6 h-6 rounded-full border-2 border-apple-blue border-t-transparent animate-spin mb-2" />
            <p className="text-xs text-neutral-400">Loading reminders...</p>
          </div>
        ) : reminders.length === 0 ? (
          <div className="py-8 text-center text-neutral-400 text-xs">
            No scheduled reminders for this conversation yet.
          </div>
        ) : (
          <div className="space-y-2 max-h-72 overflow-y-auto">
            {reminders.map((rem) => {
              const isCompleted = rem.status === 'completed'
              const isCancelled = rem.status === 'cancelled'

              return (
                <div
                  key={rem.id}
                  className={`p-3 rounded-xl border transition-colors flex items-start justify-between gap-3 ${
                    isCompleted
                      ? 'bg-neutral-50/50 dark:bg-neutral-900/30 border-neutral-200/50 opacity-70'
                      : isCancelled
                      ? 'bg-neutral-50/30 dark:bg-neutral-900/20 border-neutral-200/40 line-through opacity-50'
                      : 'bg-white dark:bg-neutral-800 border-neutral-200 dark:border-neutral-700'
                  }`}
                  data-testid={`reminder-item-${rem.id}`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className={`text-xs font-semibold ${isCompleted ? 'line-through text-neutral-500' : 'text-neutral-900 dark:text-neutral-100'}`}>
                        {rem.title}
                      </span>
                      {rem.advance_delivered && !isCompleted && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 font-medium">
                          Advance Delivered
                        </span>
                      )}
                      {rem.due_delivered && !isCompleted && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 font-medium">
                          Due
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 text-[11px] text-neutral-500 dark:text-neutral-400 flex-wrap">
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3 h-3" />
                        {formatFullDateTime(rem.due_at)}
                      </span>
                      <span>•</span>
                      <span>{rem.advance_reminder_minutes}m notice</span>
                    </div>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    <button
                      type="button"
                      onClick={() => handleToggleComplete(rem)}
                      className={`p-1.5 rounded-lg transition-colors ${
                        isCompleted
                          ? 'text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/30'
                          : 'text-neutral-400 hover:text-emerald-600 hover:bg-emerald-50 dark:hover:bg-emerald-950/30'
                      }`}
                      title={isCompleted ? 'Mark pending' : 'Mark completed'}
                      data-testid={`complete-reminder-btn-${rem.id}`}
                    >
                      <CheckCircle2 className="w-4 h-4" />
                    </button>

                    {!isCancelled && (
                      <button
                        type="button"
                        onClick={() => handleCancelReminder(rem.id)}
                        className="p-1.5 rounded-lg text-neutral-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                        title="Cancel reminder"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
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
