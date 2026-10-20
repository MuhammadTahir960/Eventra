import { Link } from 'react-router-dom'
import { StatusBadge } from '@/components/StatusBadge'
import { formatDateTime } from '@/lib/format'
import { EVENT_STATUS } from '../status'
import type { EventItem } from '../types'
import type { EventRefs } from '../lookups'
import { EventMedia } from './EventMedia'

// One link per card (the title); the whole card is clickable through the
// stretched ::after, so keyboard and screen reader users get one stop.
export function EventCard({
  event,
  refs,
  heading: Heading = 'h2',
}: {
  event: EventItem
  refs: EventRefs
  // One level below the heading the grid sits under
  heading?: 'h2' | 'h3'
}) {
  const status = EVENT_STATUS[event.status]
  const { venue } = refs

  return (
    <article className="group relative flex min-w-0 flex-col gap-3">
      <EventMedia event={event} refs={refs} className="aspect-[4/3]" />

      <div className="flex flex-col gap-1">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <time
            dateTime={event.start_datetime}
            className="tabular text-[13px] font-medium text-ember-deep"
          >
            {formatDateTime(event.start_datetime)}
          </time>
          {event.status !== 'approved' && (
            <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
          )}
        </div>
        <Heading className="line-clamp-3 font-display text-[26px] leading-[1.1] wrap-anywhere">
          {/* Clamped so cards in a row stay even; the full title is on hover and the event page */}
          <Link
            to={`/events/${event.id}`}
            title={event.title}
            className="decoration-1 underline-offset-4 outline-none group-hover:underline after:absolute after:inset-0 after:rounded-lg focus-visible:after:outline-2 focus-visible:after:outline-offset-4 focus-visible:after:outline-ring"
          >
            {event.title}
          </Link>
        </Heading>
        {venue && (
          <p className="text-sm text-muted-foreground">
            {venue.name}, {venue.city}
          </p>
        )}
      </div>
    </article>
  )
}

export function EventCardSkeleton() {
  return (
    <div aria-hidden className="flex flex-col gap-3">
      <div className="aspect-[4/3] animate-pulse rounded-lg bg-muted" />
      <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
      <div className="h-6 w-4/5 animate-pulse rounded bg-muted" />
      <div className="h-3 w-1/2 animate-pulse rounded bg-muted" />
    </div>
  )
}
