import { describe, expect, it } from 'vitest'
import type { EventItem } from '@/features/events/types'
import { canRefundPostponed } from './api'

const HOUR = 60 * 60 * 1000
const start = Date.parse('2026-11-14T14:00:00Z')
const was = '2026-11-07T14:00:00Z'

function event(
  status: EventItem['status'],
  postponed_from: string | null,
): EventItem {
  return {
    status,
    start_datetime: new Date(start).toISOString(),
    postponed_from,
  } as EventItem
}

describe('canRefundPostponed', () => {
  it('is offered until a day before the new start', () => {
    expect(canRefundPostponed(event('approved', was), start - 25 * HOUR)).toBe(
      true,
    )
    expect(canRefundPostponed(event('approved', was), start - 23 * HOUR)).toBe(
      false,
    )
  })

  it('is not offered for an event never postponed or since cancelled', () => {
    expect(canRefundPostponed(event('approved', null), start - 48 * HOUR)).toBe(
      false,
    )
    expect(canRefundPostponed(event('cancelled', was), start - 48 * HOUR)).toBe(
      false,
    )
  })
})
