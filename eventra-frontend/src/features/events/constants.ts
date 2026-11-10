import type { EventFilters } from './filters'

export const DATE_PRESETS: readonly string[] = ['weekend', 'week', 'month']

export const DEFAULT_FILTERS: EventFilters = {
  search: '',
  category: '',
  city: '',
  type: '',
  when: 'upcoming',
  dates: '',
  page: 1,
}

export const MAX_TEXT_LENGTH = 100
