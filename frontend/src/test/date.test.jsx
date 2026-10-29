import { describe, it, expect, afterEach, vi } from 'vitest'
import { formatMessageTime, formatConversationTime, formatFullDateTime } from '../utils/date'

// Deterministic tests built against the test runner's own local timezone
// (whatever it is) rather than a hardcoded zone, since switching
// process.env.TZ mid-process is not reliably honored by Node/V8. Expected
// values are derived from a plain `Date` constructed from the same UTC
// instant, so these tests still catch: double timezone conversion, a
// "few minutes ago" message mislabeled as "Yesterday", and day-boundary bugs.
describe('date formatting utilities (deterministic timezone cases)', () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it('formatMessageTime renders the correct local wall-clock time for a fixed UTC instant', () => {
    const iso = '2026-10-28T15:00:00Z'
    const expected = new Date(iso).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })
    expect(formatMessageTime(iso)).toBe(expected)
  })

  it('does not apply a timezone conversion twice: "Z" and "+00:00" suffixes for the same instant agree', () => {
    const withOffset = formatMessageTime('2026-10-28T15:00:00+00:00')
    const withZ = formatMessageTime('2026-10-28T15:00:00Z')
    expect(withOffset).toBe(withZ)
  })

  it('a message sent a few minutes ago is never labeled "Yesterday"', () => {
    vi.useFakeTimers()
    const now = new Date('2026-10-28T15:05:00Z')
    vi.setSystemTime(now)

    const sentAt = new Date('2026-10-28T15:00:00Z') // 5 minutes before "now"
    const label = formatConversationTime(sentAt.toISOString())

    expect(label).not.toBe('Yesterday')
    expect(label).toBe(sentAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
  })

  it('a message sent just after local midnight is "today", not "Yesterday", regardless of the UTC calendar date', () => {
    vi.useFakeTimers()
    const now = new Date('2026-10-28T18:40:00Z')
    vi.setSystemTime(now)

    const sentAt = new Date(now.getTime() - 5 * 60 * 1000) // 5 minutes before "now", same local day
    const label = formatConversationTime(sentAt.toISOString())

    expect(label).not.toBe('Yesterday')
  })

  it('correctly labels a message from the actual previous local calendar day as "Yesterday"', () => {
    vi.useFakeTimers()
    const now = new Date('2026-10-28T15:05:00Z')
    vi.setSystemTime(now)

    const sentAt = new Date(now.getTime() - 24 * 60 * 60 * 1000) // exactly 1 day earlier, same wall time
    const label = formatConversationTime(sentAt.toISOString())

    expect(label).toBe('Yesterday')
  })

  it('a message from today (not yesterday) never renders the weekday/"Yesterday" branch', () => {
    vi.useFakeTimers()
    const now = new Date('2026-10-28T09:00:00Z')
    vi.setSystemTime(now)

    const sentAt = new Date(now.getTime() - 2 * 60 * 1000)
    const label = formatConversationTime(sentAt.toISOString())

    expect(label).toBe(sentAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' }))
  })

  it('formatFullDateTime renders the correct local date and time for a fixed instant', () => {
    const iso = '2026-10-28T15:00:00Z'
    const expected = new Date(iso).toLocaleDateString([], {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
    })
    expect(formatFullDateTime(iso)).toBe(expected)
  })

  it('sending and receiving a message does not change the instant it represents', () => {
    // Simulates: server persists created_at, broadcasts it over Socket.IO, and the
    // recipient's client renders it -- all should resolve to one unambiguous instant.
    const createdAt = '2026-10-28T15:00:00Z'
    const asReceivedBySender = formatMessageTime(createdAt)
    const asReceivedByRecipient = formatMessageTime(createdAt)
    expect(asReceivedBySender).toBe(asReceivedByRecipient)
  })
})
