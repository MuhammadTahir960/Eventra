import { useQuery } from '@tanstack/react-query'
import { fetchAllPages } from '@/lib/pagination'
import type { Category, League, Team, Venue } from './types'

// Reference data changes rarely, so keep it fresh for 5 minutes
const REFERENCE_STALE_MS = 5 * 60_000

// The event API returns bare IDs for venue/category/teams, so pages load
// these lists once and look names, photos and cities up by ID.
function toMap<T extends { id: string }>(items: T[]): Map<string, T> {
  return new Map(items.map((item) => [item.id, item]))
}

export function useVenues() {
  return useQuery({
    queryKey: ['catalog', 'venues'],
    queryFn: ({ signal }) => fetchAllPages<Venue>('/venues/', {}, signal),
    staleTime: REFERENCE_STALE_MS,
    select: (venues) => ({ list: venues, byId: toMap(venues) }),
  })
}

export function useCategories() {
  return useQuery({
    queryKey: ['catalog', 'categories'],
    queryFn: ({ signal }) =>
      fetchAllPages<Category>('/categories/', {}, signal),
    staleTime: REFERENCE_STALE_MS,
    select: (categories) => ({
      list: [...categories].sort((a, b) => a.sort_order - b.sort_order),
      byId: toMap(categories),
    }),
  })
}

// Only sports matches need these, so callers can switch them off
export function useTeams(enabled = true) {
  return useQuery({
    queryKey: ['catalog', 'teams'],
    queryFn: ({ signal }) => fetchAllPages<Team>('/teams/', {}, signal),
    staleTime: REFERENCE_STALE_MS,
    enabled,
    select: toMap,
  })
}

export function useLeagues(enabled = true) {
  return useQuery({
    queryKey: ['catalog', 'leagues'],
    queryFn: ({ signal }) => fetchAllPages<League>('/leagues/', {}, signal),
    staleTime: REFERENCE_STALE_MS,
    enabled,
    select: toMap,
  })
}
