import { useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { ApiError } from '@/lib/api-client'
import { MatchRow } from '../components/MatchRow'
import { DEFAULT_FILTERS } from '../filters'
import { useEvents } from '../hooks'
import { bySoonest, useEventLookups } from '../lookups'
import type { EventItem } from '../types'
import { usePageTitle } from '@/lib/use-page-title'

const dayHeading = new Intl.DateTimeFormat(undefined, {
  weekday: 'long',
  day: 'numeric',
  month: 'long',
})

// Fixtures grouped by local calendar day, like a printed programme
function groupByDay(events: EventItem[]): [string, EventItem[]][] {
  const groups = new Map<string, EventItem[]>()
  for (const item of events) {
    const key = new Date(item.start_datetime).toDateString()
    groups.set(key, [...(groups.get(key) ?? []), item])
  }
  return [...groups.entries()]
}

export function SportsPage() {
  usePageTitle('Sports')
  const [params, setParams] = useSearchParams()
  const pageParam = Number(params.get('page'))
  const page = Number.isInteger(pageParam) && pageParam > 1 ? pageParam : 1

  const matches = useEvents({ ...DEFAULT_FILTERS, type: 'sports_match', page })
  const results = matches.data?.results
  const { resolve } = useEventLookups(results)
  const days = useMemo(
    () => groupByDay([...(results ?? [])].sort(bySoonest)),
    [results],
  )

  return (
    <div className="gutter mx-auto flex max-w-[1200px] flex-col gap-10 pt-10 sm:pt-14">
      <PageHeader
        title="Sports"
        description="Every upcoming fixture with tickets on sale."
      />

      {matches.isError ? (
        <Notice tone="error">
          {matches.error instanceof ApiError
            ? matches.error.message
            : 'Matches could not be loaded.'}{' '}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => void matches.refetch()}
          >
            Try again
          </button>
        </Notice>
      ) : matches.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading matches"
          className="flex flex-col gap-3"
        >
          {Array.from({ length: 5 }, (_, index) => (
            <div key={index} className="h-14 animate-pulse rounded bg-muted" />
          ))}
        </div>
      ) : days.length === 0 ? (
        <EmptyState
          title="No matches scheduled"
          body="Fixtures appear here once they're approved and on sale."
        />
      ) : (
        <>
          {days.map(([key, items]) => (
            <section key={key} aria-label={dayHeading.format(new Date(key))}>
              <h2 className="pb-2 text-sm font-medium">
                {dayHeading.format(new Date(key))}
              </h2>
              <ul className="border-t border-ink">
                {items.map((item) => (
                  <MatchRow key={item.id} event={item} refs={resolve(item)} />
                ))}
              </ul>
            </section>
          ))}
          <Pagination
            page={page}
            count={matches.data.count}
            hasPrevious={Boolean(matches.data.previous)}
            hasNext={Boolean(matches.data.next)}
            onPage={(next) => setParams(next > 1 ? { page: String(next) } : {})}
          />
        </>
      )}
    </div>
  )
}
