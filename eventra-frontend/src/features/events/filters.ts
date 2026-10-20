import { isUuid } from '@/lib/ids'
import type { EventType } from './types'

// "upcoming" = approved events that haven't started; "past" = completed ones
export type EventWhen = 'upcoming' | 'past'

// Date presets for upcoming events (the API takes date_from / date_to)
export type EventDates = '' | 'weekend' | 'week' | 'month'
const DATE_PRESETS: readonly string[] = ['weekend', 'week', 'month']

export interface EventFilters {
  search: string
  category: string
  city: string
  type: EventType | ''
  when: EventWhen
  dates: EventDates
  page: number
}

export const DEFAULT_FILTERS: EventFilters = {
  search: '',
  category: '',
  city: '',
  type: '',
  when: 'upcoming',
  dates: '',
  page: 1,
}

const MAX_TEXT_LENGTH = 100

// The URL is user-editable, so every value is checked against an allow-list
// before it is used. Anything unrecognised falls back to the default.
export function parseFilters(params: URLSearchParams): EventFilters {
  const type = params.get('type')
  const category = params.get('category') ?? ''
  const page = Number(params.get('page'))
  const dates = params.get('dates') ?? ''

  return {
    search: (params.get('q') ?? '').slice(0, MAX_TEXT_LENGTH),
    category: isUuid(category) ? category : '',
    city: (params.get('city') ?? '').slice(0, MAX_TEXT_LENGTH),
    type: type === 'general' || type === 'sports_match' ? type : '',
    when: params.get('when') === 'past' ? 'past' : 'upcoming',
    dates: DATE_PRESETS.includes(dates) ? (dates as EventDates) : '',
    page: Number.isInteger(page) && page > 1 ? page : 1,
  }
}

// Only non-default values go in the URL, keeping shared links short
export function toSearchParams(filters: EventFilters): URLSearchParams {
  const params = new URLSearchParams()
  if (filters.search) params.set('q', filters.search)
  if (filters.category) params.set('category', filters.category)
  if (filters.city) params.set('city', filters.city)
  if (filters.type) params.set('type', filters.type)
  if (filters.when !== 'upcoming') params.set('when', filters.when)
  if (filters.dates) params.set('dates', filters.dates)
  if (filters.page > 1) params.set('page', String(filters.page))
  return params
}

// Query for GET /events/. `now` is passed in (rounded to the hour by the
// caller) so the request key stays stable between renders.
export function toApiQuery(filters: EventFilters, nowIso: string) {
  return {
    search: filters.search.trim(),
    category: filters.category,
    city: filters.city,
    event_type: filters.type,
    page: filters.page,
    ...(filters.when === 'upcoming'
      ? {
          status: 'approved',
          date_from: nowIso,
          date_to: presetEnd(filters.dates, new Date(nowIso)),
        }
      : { status: 'completed' }),
  }
}

const DAY_MS = 24 * 60 * 60 * 1000

// Upper bound for a date preset, in the viewer's local time. "weekend" ends
// at the start of the coming Monday, so on a Saturday or Sunday it covers
// the rest of the current weekend.
export function presetEnd(dates: EventDates, now: Date): string | undefined {
  if (dates === 'week')
    return new Date(now.getTime() + 7 * DAY_MS).toISOString()
  if (dates === 'month')
    return new Date(now.getTime() + 30 * DAY_MS).toISOString()
  if (dates === 'weekend') {
    const monday = new Date(now)
    monday.setHours(0, 0, 0, 0)
    // getDay(): Sunday 0 ... Saturday 6. Days until the next Monday (1..7).
    const daysToMonday = (8 - monday.getDay()) % 7 || 7
    monday.setDate(monday.getDate() + daysToMonday)
    return monday.toISOString()
  }
  return undefined
}

// Start of the current hour as an ISO string
export function startOfHourIso(date: Date = new Date()): string {
  const rounded = new Date(date)
  rounded.setMinutes(0, 0, 0)
  return rounded.toISOString()
}
