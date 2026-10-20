import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { ApiError } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { EventCard, EventCardSkeleton } from '../components/EventCard'
import { EventFiltersBar } from '../components/EventFiltersBar'
import { parseFilters, toSearchParams, type EventFilters } from '../filters'
import { useEvents } from '../hooks'
import { bySoonest, useEventLookups } from '../lookups'
import { usePageTitle } from '@/lib/use-page-title'

export function EventsPage() {
  usePageTitle('Events')
  const [params, setParams] = useSearchParams()
  const filters = useMemo(() => parseFilters(params), [params])

  const events = useEvents(filters)
  const results = events.data?.results
  const { resolve, venues, categories } = useEventLookups(results)

  const cities = useMemo(
    () =>
      [...new Set((venues.data?.list ?? []).map((venue) => venue.city))].sort(),
    [venues.data],
  )

  // Upcoming reads soonest first; past keeps the API's newest-first order
  const ordered = useMemo(() => {
    if (!results) return []
    return filters.when === 'past' ? results : [...results].sort(bySoonest)
  }, [results, filters.when])

  function updateFilters(changes: Partial<EventFilters>) {
    // Any filter change goes back to page 1; paging changes keep their page
    setParams(toSearchParams({ ...filters, page: 1, ...changes }))
  }

  const pageOutOfRange =
    events.error instanceof ApiError &&
    events.error.status === 404 &&
    filters.page > 1

  return (
    <div className="gutter mx-auto flex max-w-[1200px] flex-col gap-8 pt-10 sm:pt-14">
      <PageHeader
        title={filters.when === 'past' ? 'Past events' : 'Events'}
        description={
          events.data
            ? `${events.data.count.toLocaleString()} ${events.data.count === 1 ? 'event' : 'events'}`
            : undefined
        }
      />

      <EventFiltersBar
        filters={filters}
        categories={categories.data?.list ?? []}
        cities={cities}
        autoFocusSearch={params.get('focus') === 'search'}
        onChange={updateFilters}
      />

      {pageOutOfRange ? (
        <Notice>
          That page doesn't exist.{' '}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => updateFilters({ page: 1 })}
          >
            Go to the first page
          </button>
        </Notice>
      ) : events.isError ? (
        <Notice tone="error">
          {events.error instanceof ApiError
            ? events.error.message
            : 'Events could not be loaded.'}{' '}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => void events.refetch()}
          >
            Try again
          </button>
        </Notice>
      ) : events.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading events"
          className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-3"
        >
          {Array.from({ length: 6 }, (_, index) => (
            <EventCardSkeleton key={index} />
          ))}
        </div>
      ) : ordered.length === 0 ? (
        <EmptyState
          title="No events match"
          body="Try another search, or clear the filters to see everything on sale."
        />
      ) : (
        <>
          <div
            className={cn(
              'grid gap-x-6 gap-y-10 transition-opacity sm:grid-cols-2 lg:grid-cols-3',
              events.isPlaceholderData && 'opacity-60',
            )}
          >
            {ordered.map((item) => (
              <EventCard key={item.id} event={item} refs={resolve(item)} />
            ))}
          </div>
          <Pagination
            page={filters.page}
            count={events.data.count}
            hasPrevious={Boolean(events.data.previous)}
            hasNext={Boolean(events.data.next)}
            onPage={(page) => updateFilters({ page })}
          />
        </>
      )}
    </div>
  )
}
