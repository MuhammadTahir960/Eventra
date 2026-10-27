import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import { useAuth } from '@/features/auth/auth-store'
import { apiFetch } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import type { Page } from '@/lib/pagination'
import { toApiQuery, startOfHourIso, type EventFilters } from './filters'
import type { EventItem, TicketTier } from './types'

export function useEvents(filters: EventFilters) {
  // Stable for the life of the page so the query key doesn't change each render
  const nowIso = useMemo(() => startOfHourIso(), [])

  return useQuery({
    queryKey: ['events', 'list', filters, nowIso],
    queryFn: ({ signal }) =>
      apiFetch<Page<EventItem>>('/events/', {
        // The key stays per-hour, but the lower bound is the real now so events that already started drop out
        query: toApiQuery(filters, new Date().toISOString()),
        signal,
      }),
    // Keep the old results on screen while the next page or filter loads
    placeholderData: keepPreviousData,
  })
}

// Owners, admins and ticket holders can see some non-public events, so after a
// reload wait for the saved session instead of asking as an anonymous visitor
function useSessionReady() {
  return useAuth().status === 'ready'
}

// The id comes from the address bar, so check its shape before calling the API
export function useEvent(id: string | undefined) {
  const ready = useSessionReady()
  return useQuery({
    queryKey: ['events', 'detail', id],
    queryFn: ({ signal }) => apiFetch<EventItem>(`/events/${id}/`, { signal }),
    enabled: ready && isUuid(id),
    retry: false,
  })
}

export function useTicketTiers(id: string | undefined) {
  const ready = useSessionReady()
  return useQuery({
    queryKey: ['events', 'tiers', id],
    queryFn: ({ signal }) =>
      apiFetch<TicketTier[]>(`/events/${id}/ticket-tiers/`, { signal }),
    enabled: ready && isUuid(id),
  })
}
