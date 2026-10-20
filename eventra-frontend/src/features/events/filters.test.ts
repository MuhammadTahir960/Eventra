import { describe, expect, it } from 'vitest'
import {
  DEFAULT_FILTERS,
  parseFilters,
  presetEnd,
  toApiQuery,
  toSearchParams,
} from './filters'

const UUID = '3f0c1a2e-8b7d-4c6e-9a10-5d2b7c9e4f11'

describe('parseFilters', () => {
  it('uses defaults for an empty URL', () => {
    expect(parseFilters(new URLSearchParams())).toEqual(DEFAULT_FILTERS)
  })

  it('reads valid values', () => {
    const filters = parseFilters(
      new URLSearchParams(
        `q=derby&category=${UUID}&city=Karachi&type=sports_match&when=past&dates=week&page=3`,
      ),
    )
    expect(filters).toEqual({
      search: 'derby',
      category: UUID,
      city: 'Karachi',
      type: 'sports_match',
      when: 'past',
      dates: 'week',
      page: 3,
    })
  })

  it('drops values that fail the allow-list', () => {
    const filters = parseFilters(
      new URLSearchParams(
        'category=not-a-uuid&type=hacked&when=x&dates=year&page=-4',
      ),
    )
    expect(filters).toEqual(DEFAULT_FILTERS)
  })

  it('caps search text length', () => {
    const filters = parseFilters(new URLSearchParams(`q=${'a'.repeat(500)}`))
    expect(filters.search).toHaveLength(100)
  })
})

describe('toSearchParams', () => {
  it('omits defaults so links stay short', () => {
    expect(toSearchParams(DEFAULT_FILTERS).toString()).toBe('')
  })

  it('round-trips through parseFilters', () => {
    const filters = {
      ...DEFAULT_FILTERS,
      search: 'derby',
      city: 'Lahore',
      when: 'past' as const,
      dates: 'weekend' as const,
      page: 2,
    }
    expect(parseFilters(toSearchParams(filters))).toEqual(filters)
  })
})

describe('toApiQuery', () => {
  const now = '2026-10-12T10:00:00.000Z'

  it('asks for approved events starting from now when upcoming', () => {
    expect(toApiQuery(DEFAULT_FILTERS, now)).toMatchObject({
      status: 'approved',
      date_from: now,
    })
  })

  it('asks for completed events when past, with no start bound', () => {
    const query = toApiQuery({ ...DEFAULT_FILTERS, when: 'past' }, now)
    expect(query).toMatchObject({ status: 'completed' })
    expect(query).not.toHaveProperty('date_from')
  })

  it('maps the type filter to the backend name', () => {
    const query = toApiQuery({ ...DEFAULT_FILTERS, type: 'general' }, now)
    expect(query.event_type).toBe('general')
  })
})

describe('presetEnd', () => {
  // Local-time dates so the weekday maths matches the viewer's calendar
  const wednesday = new Date(2026, 9, 14, 10)
  const saturday = new Date(2026, 9, 17, 10)
  const sunday = new Date(2026, 9, 18, 10)
  const nextMonday = new Date(2026, 9, 19)

  it('has no upper bound without a preset', () => {
    expect(presetEnd('', wednesday)).toBeUndefined()
  })

  it('ends the weekend at the start of the coming Monday', () => {
    expect(presetEnd('weekend', wednesday)).toBe(nextMonday.toISOString())
    expect(presetEnd('weekend', saturday)).toBe(nextMonday.toISOString())
    expect(presetEnd('weekend', sunday)).toBe(nextMonday.toISOString())
  })

  it('on a Monday, looks ahead to the following weekend', () => {
    expect(presetEnd('weekend', nextMonday)).toBe(
      new Date(2026, 9, 26).toISOString(),
    )
  })

  it('spans 7 and 30 days for week and month', () => {
    const day = 24 * 60 * 60 * 1000
    expect(presetEnd('week', wednesday)).toBe(
      new Date(wednesday.getTime() + 7 * day).toISOString(),
    )
    expect(presetEnd('month', wednesday)).toBe(
      new Date(wednesday.getTime() + 30 * day).toISOString(),
    )
  })

  it('is sent as date_to for upcoming events only', () => {
    const now = wednesday.toISOString()
    expect(
      toApiQuery({ ...DEFAULT_FILTERS, dates: 'week' }, now),
    ).toMatchObject({ date_to: presetEnd('week', wednesday) })
    expect(
      toApiQuery({ ...DEFAULT_FILTERS, when: 'past', dates: 'week' }, now),
    ).not.toHaveProperty('date_to')
  })
})
