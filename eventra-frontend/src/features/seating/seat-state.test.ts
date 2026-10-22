import { describe, expect, it } from 'vitest'
import {
  applySeatMessage,
  parseSeatMessage,
  takenFromSelection,
} from './seat-state'
import type { EventSeat } from './types'

const seat = (id: string, status: EventSeat['status']): EventSeat => ({
  id,
  section: 'A',
  row_label: 'A',
  seat_number: 1,
  ticket_tier: 't',
  tier_name: 'VIP',
  price: '50.00',
  status,
})

describe('parseSeatMessage', () => {
  it('accepts a snapshot and an update', () => {
    const body = JSON.stringify({
      type: 'seat_update',
      seats: [seat('s1', 'held')],
    })
    expect(parseSeatMessage(body)).toEqual({
      type: 'seat_update',
      seats: [seat('s1', 'held')],
    })
    expect(
      parseSeatMessage(JSON.stringify({ type: 'initial_state', seats: [] })),
    ).toEqual({ type: 'initial_state', seats: [] })
  })

  it.each([
    ['not json', 'nope'],
    ['a json string', '"hello"'],
    ['an unknown type', JSON.stringify({ type: 'hack', seats: [] })],
    ['missing seats', JSON.stringify({ type: 'seat_update' })],
    ['seats not an array', JSON.stringify({ type: 'seat_update', seats: 'x' })],
    [
      'a seat with a made-up status',
      JSON.stringify({
        type: 'seat_update',
        seats: [{ ...seat('s1', 'held'), status: 'free' }],
      }),
    ],
    [
      'a seat with no id',
      JSON.stringify({ type: 'seat_update', seats: [{ section: 'A' }] }),
    ],
  ])('rejects %s', (_label, body) => {
    expect(parseSeatMessage(body)).toBeNull()
  })
})

describe('applySeatMessage', () => {
  const current = [seat('s1', 'available'), seat('s2', 'available')]

  it('replaces everything on a snapshot', () => {
    const next = applySeatMessage(current, {
      type: 'initial_state',
      seats: [seat('s9', 'booked')],
    })
    expect(next).toEqual([seat('s9', 'booked')])
  })

  it('changes only the seats an update names', () => {
    const next = applySeatMessage(current, {
      type: 'seat_update',
      seats: [seat('s2', 'held')],
    })
    expect(next?.map((s) => s.status)).toEqual(['available', 'held'])
  })

  it('does not mutate the previous state', () => {
    applySeatMessage(current, {
      type: 'seat_update',
      seats: [seat('s1', 'booked')],
    })
    expect(current[0].status).toBe('available')
  })

  it('ignores updates for seats it does not know', () => {
    const next = applySeatMessage(current, {
      type: 'seat_update',
      seats: [seat('other', 'held')],
    })
    expect(next).toEqual(current)
  })

  it('waits for the base map before applying updates', () => {
    expect(
      applySeatMessage(undefined, {
        type: 'seat_update',
        seats: [seat('s1', 'held')],
      }),
    ).toBeUndefined()
  })

  it('still accepts a snapshot before the base map loads', () => {
    expect(
      applySeatMessage(undefined, {
        type: 'initial_state',
        seats: [seat('s1', 'held')],
      }),
    ).toEqual([seat('s1', 'held')])
  })
})

describe('takenFromSelection', () => {
  it('finds selected seats someone else took', () => {
    const seats = [
      seat('s1', 'held'),
      seat('s2', 'available'),
      seat('s3', 'booked'),
    ]
    const taken = takenFromSelection(seats, new Set(['s1', 's2', 's3']))
    expect(taken.map((s) => s.id)).toEqual(['s1', 's3'])
  })

  it('ignores seats that were not selected', () => {
    expect(takenFromSelection([seat('s1', 'held')], new Set())).toEqual([])
  })
})
