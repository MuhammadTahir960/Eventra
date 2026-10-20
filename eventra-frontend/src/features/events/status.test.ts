import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { bookingBlocker } from './status'
import type { EventItem } from './types'

// Only the fields bookingBlocker reads; the rest of EventItem is irrelevant
function makeEvent(overrides: Partial<EventItem>): EventItem {
  return {
    status: 'approved',
    is_seated: true,
    start_datetime: '2026-11-01T18:00:00Z',
    ...overrides,
  } as EventItem
}

describe('bookingBlocker', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-12T10:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('allows a seated, approved, future event', () => {
    expect(bookingBlocker(makeEvent({}))).toBeNull()
  })

  it('blocks events that are not on sale', () => {
    expect(bookingBlocker(makeEvent({ status: 'pending_approval' }))).toBe(
      'not_on_sale',
    )
    expect(bookingBlocker(makeEvent({ status: 'cancelled' }))).toBe(
      'not_on_sale',
    )
  })

  it('blocks events without a seat map', () => {
    expect(bookingBlocker(makeEvent({ is_seated: false }))).toBe('not_seated')
  })

  it('blocks events that have already started', () => {
    expect(
      bookingBlocker(makeEvent({ start_datetime: '2026-10-12T09:00:00Z' })),
    ).toBe('started')
  })
})
