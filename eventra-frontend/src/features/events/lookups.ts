import { useCallback } from 'react'
import { useCategories, useTeams, useVenues } from '@/features/catalog/hooks'
import type { Category, Team, Venue } from '@/features/catalog/types'
import type { EventItem } from './types'

export interface EventRefs {
  venue: Venue | undefined
  category: Category | undefined
  home: Team | undefined
  away: Team | undefined
}

// The event API returns bare ids for venue, category and teams. This loads
// the reference lists once and resolves an event's ids against them.
export function useEventLookups(events: EventItem[] | undefined) {
  const venues = useVenues()
  const categories = useCategories()
  // Team lists are only needed when a sports match is on screen
  const hasMatches = events?.some((item) => item.event_type === 'sports_match')
  const teams = useTeams(Boolean(hasMatches))

  const resolve = useCallback(
    (event: EventItem): EventRefs => ({
      venue: event.venue ? venues.data?.byId.get(event.venue) : undefined,
      category: event.category
        ? categories.data?.byId.get(event.category)
        : undefined,
      home: event.home_team ? teams.data?.get(event.home_team) : undefined,
      away: event.away_team ? teams.data?.get(event.away_team) : undefined,
    }),
    [venues.data, categories.data, teams.data],
  )

  return { resolve, venues, categories }
}

// The API lists newest first and has no ordering parameter, so upcoming
// events are sorted soonest first on the client.
export function bySoonest(a: EventItem, b: EventItem): number {
  return (
    new Date(a.start_datetime).getTime() - new Date(b.start_datetime).getTime()
  )
}
