import { describe, expect, it } from 'vitest'
import type { EventItem } from '@/features/events/types'
import { canPostpone, canRunLate } from './running-late'

const HOUR = 60 * 60 * 1000
const start = Date.parse('2026-11-01T14:00:00Z')

function event(status: EventItem['status']): EventItem {
  return {
    status,
    start_datetime: new Date(start).toISOString(),
  } as EventItem
}

describe('canRunLate', () => {
  it('is offered from a day before the start', () => {
    expect(canRunLate(event('approved'), start - 25 * HOUR)).toBe(false)
    expect(canRunLate(event('approved'), start - 23 * HOUR)).toBe(true)
    expect(canRunLate(event('approved'), start + 5 * HOUR)).toBe(true)
  })

  it('also covers an event back in review', () => {
    expect(canRunLate(event('pending_approval'), start)).toBe(true)
  })

  it('is never offered once the event is finished or off sale', () => {
    for (const status of ['completed', 'cancelled', 'rejected'] as const)
      expect(canRunLate(event(status), start)).toBe(false)
  })
})

describe('canPostpone', () => {
  it('is offered until the event starts', () => {
    expect(canPostpone(event('approved'), start - HOUR)).toBe(true)
    expect(canPostpone(event('pending_approval'), start - HOUR)).toBe(true)
    expect(canPostpone(event('approved'), start)).toBe(false)
    expect(canPostpone(event('cancelled'), start - HOUR)).toBe(false)
  })
})
