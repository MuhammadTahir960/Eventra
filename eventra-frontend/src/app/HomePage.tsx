import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { useAuth } from '@/features/auth/auth-store'
import {
  EventCard,
  EventCardSkeleton,
} from '@/features/events/components/EventCard'
import { EventMedia } from '@/features/events/components/EventMedia'
import { MatchRow } from '@/features/events/components/MatchRow'
import { DEFAULT_FILTERS } from '@/features/events/filters'
import { useEvents } from '@/features/events/hooks'
import { bySoonest, useEventLookups } from '@/features/events/lookups'
import { formatDateTimeLong } from '@/lib/format'
import { usePageTitle } from '@/lib/use-page-title'

function SectionHeading({
  id,
  title,
  to,
  linkLabel,
}: {
  id: string
  title: string
  to: string
  linkLabel: string
}) {
  return (
    <div className="flex items-end justify-between gap-4">
      <h2
        id={id}
        className="font-display text-[clamp(2rem,4vw,2.5rem)] leading-none"
      >
        {title}
      </h2>
      <Link
        to={to}
        className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-ember-deep underline-offset-4 hover:underline"
      >
        {linkLabel}
        <HugeiconsIcon icon={ArrowRight01Icon} size={16} aria-hidden />
      </Link>
    </div>
  )
}

export function HomePage() {
  usePageTitle(undefined)
  const { user } = useAuth()
  const upcoming = useEvents(DEFAULT_FILTERS)
  const matches = useEvents({ ...DEFAULT_FILTERS, type: 'sports_match' })
  const { resolve, venues, categories } = useEventLookups([
    ...(upcoming.data?.results ?? []),
    ...(matches.data?.results ?? []),
  ])

  const sorted = useMemo(
    () => [...(upcoming.data?.results ?? [])].sort(bySoonest),
    [upcoming.data],
  )
  // No "featured" flag in the API: lead with the soonest event whose venue
  // has a photo, falling back to the soonest event of all
  const featured = useMemo(() => {
    const withPhoto = sorted.find((item) => {
      const venue = item.venue ? venues.data?.byId.get(item.venue) : undefined
      return Boolean(venue?.photo)
    })
    return withPhoto ?? sorted[0]
  }, [sorted, venues.data])
  const next = sorted.filter((item) => item !== featured).slice(0, 4)
  const fixtures = [...(matches.data?.results ?? [])]
    .sort(bySoonest)
    .slice(0, 5)

  return (
    <div className="gutter mx-auto flex max-w-[1200px] flex-col gap-20 pt-10 sm:pt-14">
      <section aria-labelledby="whats-on" className="flex flex-col gap-8">
        <h1
          id="whats-on"
          className="font-display text-[clamp(2.75rem,7vw,4.5rem)] leading-none"
        >
          What's on
        </h1>

        {upcoming.isPending ? (
          <div
            aria-busy="true"
            aria-label="Loading events"
            className="aspect-[4/3] animate-pulse rounded-lg bg-muted sm:aspect-[21/9]"
          />
        ) : upcoming.isError ? (
          <EmptyState
            title="Events could not be loaded"
            body="Check your connection and try again."
            action={
              <Button variant="outline" onClick={() => void upcoming.refetch()}>
                Try again
              </Button>
            }
          />
        ) : !featured ? (
          <EmptyState
            title="Nothing on sale yet"
            body="New events appear here as soon as they're approved."
          />
        ) : (
          <article className="group relative grid items-center gap-6 lg:grid-cols-[minmax(0,1.45fr)_minmax(0,1fr)] lg:gap-12">
            <EventMedia
              event={featured}
              refs={resolve(featured)}
              eager
              className="aspect-[4/3]"
            />
            <div className="flex flex-col gap-4">
              <p className="text-sm text-muted-foreground">Next up</p>
              <h2 className="font-display text-[clamp(2.5rem,5vw,3.75rem)] leading-[1.02] wrap-anywhere">
                <Link
                  to={`/events/${featured.id}`}
                  className="outline-none after:absolute after:inset-0 focus-visible:underline"
                >
                  {featured.title}
                </Link>
              </h2>
              <div className="flex flex-col gap-1 text-[15px]">
                <time
                  dateTime={featured.start_datetime}
                  className="tabular font-medium text-ember-deep"
                >
                  {formatDateTimeLong(featured.start_datetime)}
                </time>
                {resolve(featured).venue && (
                  <span className="text-muted-foreground">
                    {resolve(featured).venue?.name},{' '}
                    {resolve(featured).venue?.city}
                  </span>
                )}
              </div>
              {/* Decorative: the whole card is already the link */}
              <span
                aria-hidden
                className="mt-2 inline-flex h-12 w-fit items-center rounded-md bg-ember-deep px-5 text-[15px] font-medium text-white transition-colors group-hover:bg-ember-deeper"
              >
                Get tickets
              </span>
            </div>
          </article>
        )}
      </section>

      {(upcoming.isPending || next.length > 0) && (
        <section aria-labelledby="coming-up" className="flex flex-col gap-8">
          <SectionHeading
            id="coming-up"
            title="Coming up"
            to="/events"
            linkLabel="All events"
          />
          <div className="grid gap-x-6 gap-y-10 sm:grid-cols-2 lg:grid-cols-4">
            {upcoming.isPending
              ? Array.from({ length: 4 }, (_, index) => (
                  <EventCardSkeleton key={index} />
                ))
              : next.map((item) => (
                  <EventCard
                    key={item.id}
                    event={item}
                    refs={resolve(item)}
                    heading="h3"
                  />
                ))}
          </div>
        </section>
      )}

      {(categories.data?.list.length ?? 0) > 0 && (
        <section aria-labelledby="browse" className="flex flex-col gap-5">
          <h2
            id="browse"
            className="font-display text-[clamp(2rem,4vw,2.5rem)] leading-none"
          >
            Browse by category
          </h2>
          <ul className="flex flex-wrap gap-2">
            {categories.data?.list.map((category) => (
              <li key={category.id}>
                <Link
                  to={`/events?category=${category.id}`}
                  className="inline-flex h-10 items-center rounded-full border border-hairline-strong bg-card px-4 text-[15px] transition-colors hover:border-ink"
                >
                  {category.name}
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {fixtures.length > 0 && (
        <section aria-labelledby="fixtures" className="flex flex-col gap-6">
          <SectionHeading
            id="fixtures"
            title="Upcoming matches"
            to="/sports"
            linkLabel="All matches"
          />
          <ul className="border-t border-border">
            {fixtures.map((item) => (
              <MatchRow
                key={item.id}
                event={item}
                refs={resolve(item)}
                showDay
              />
            ))}
          </ul>
        </section>
      )}

      {!user && (
        <section className="flex flex-col items-start gap-5 rounded-lg bg-ink px-6 py-10 text-paper sm:flex-row sm:items-center sm:justify-between sm:px-10">
          <div className="flex flex-col gap-2">
            <h2 className="font-display text-[clamp(2rem,4vw,2.5rem)] leading-none">
              Selling tickets?
            </h2>
            <p className="max-w-md text-[15px] text-[#c9c7c0]">
              Create an organizer account, list your event with a real seat map,
              and track sales and payouts.
            </p>
          </div>
          <ButtonLink
            className="bg-paper text-ink hover:bg-paper/90"
            size="lg"
            to="/register?role=organizer"
          >
            Become an organizer
          </ButtonLink>
        </section>
      )}
    </div>
  )
}
