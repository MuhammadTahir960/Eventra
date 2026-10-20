import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowRight01Icon } from '@hugeicons/core-free-icons'
import { Link } from 'react-router-dom'
import type { Team } from '@/features/catalog/types'
import type { EventRefs } from '../lookups'
import type { EventItem } from '../types'
import { ImageWithFallback } from '@/components/ImageWithFallback'
import { initial } from '@/lib/initial'

const timeFormat = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
})
const dayFormat = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
})

function TeamName({ team }: { team: Team | undefined }) {
  if (!team)
    return <span className="text-muted-foreground">To be confirmed</span>
  const letter = (
    <span
      aria-hidden
      className="grid size-6 shrink-0 place-items-center rounded-full bg-muted text-[11px] font-medium"
    >
      {initial(team.name)}
    </span>
  )
  return (
    <span className="inline-flex min-w-0 items-center gap-2">
      {team.logo ? (
        <ImageWithFallback
          src={team.logo}
          alt=""
          loading="lazy"
          fallback={letter}
          className="size-6 shrink-0 object-contain"
        />
      ) : (
        letter
      )}
      <span className="truncate">{team.name}</span>
    </span>
  )
}

// One fixture as a list row: when, who, where. The whole row is the link.
export function MatchRow({
  event,
  refs,
  showDay = false,
}: {
  event: EventItem
  refs: EventRefs
  showDay?: boolean
}) {
  const start = new Date(event.start_datetime)
  return (
    <li>
      <Link
        to={`/events/${event.id}`}
        className="group grid grid-cols-[4.5rem_minmax(0,1fr)_auto] items-center gap-4 border-b border-border py-4 hover:bg-card sm:grid-cols-[6rem_minmax(0,1fr)_minmax(0,14rem)_auto] sm:px-2"
      >
        <time dateTime={event.start_datetime} className="tabular text-sm">
          {showDay && (
            <span className="block text-muted-foreground">
              {dayFormat.format(start)}
            </span>
          )}
          <span className="font-medium">{timeFormat.format(start)}</span>
        </time>
        <span className="flex min-w-0 flex-col gap-1.5 text-[15px] font-medium sm:flex-row sm:items-center sm:gap-3">
          <TeamName team={refs.home} />
          <span className="hidden text-muted-foreground sm:inline">v</span>
          <TeamName team={refs.away} />
        </span>
        <span className="hidden truncate text-sm text-muted-foreground sm:block">
          {refs.venue ? `${refs.venue.name}, ${refs.venue.city}` : ''}
        </span>
        <HugeiconsIcon
          icon={ArrowRight01Icon}
          size={18}
          aria-hidden
          className="text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-foreground motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
        />
        <span className="sr-only">Tickets for {event.title}</span>
      </Link>
    </li>
  )
}
