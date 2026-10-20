import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowLeft01Icon } from '@hugeicons/core-free-icons'
import { Link, useParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { StatusBadge } from '@/components/StatusBadge'
import { TicketStub } from '@/components/TicketStub'
import { ButtonLink } from '@/components/ui/button-link'
import { useLeagues } from '@/features/catalog/hooks'
import { ApiError } from '@/lib/api-client'
import { formatDateTimeLong, formatMoney } from '@/lib/format'
import { isUuid } from '@/lib/ids'
import { toCents } from '@/lib/money'
import { EventMedia } from '../components/EventMedia'
import { useEvent, useTicketTiers } from '../hooks'
import { useEventLookups } from '../lookups'
import { BLOCKER_MESSAGE, EVENT_STATUS, bookingBlocker } from '../status'
import type { TicketTier } from '../types'
import { usePageTitle } from '@/lib/use-page-title'

function NotFound() {
  return (
    <div className="gutter mx-auto max-w-[1200px] pt-16">
      <EmptyState
        title="Event not found"
        body="It may have been removed, or the link is wrong."
        action={
          <ButtonLink variant="ink" to="/events">
            Browse events
          </ButtonLink>
        }
      />
    </div>
  )
}

function lowestPrice(tiers: TicketTier[]): string | null {
  if (tiers.length === 0) return null
  return tiers.reduce((low, tier) =>
    toCents(tier.price) < toCents(low.price) ? tier : low,
  ).price
}

export function EventDetailPage() {
  const { id } = useParams()
  const event = useEvent(id)
  usePageTitle(event.data?.title)
  const tiers = useTicketTiers(id)
  const { resolve } = useEventLookups(event.data ? [event.data] : undefined)
  const isMatch = event.data?.event_type === 'sports_match'
  const leagues = useLeagues(isMatch)

  // Malformed ids never reach the API; the query is disabled for them
  if (!isUuid(id)) return <NotFound />

  if (event.isPending) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading event"
        className="gutter mx-auto max-w-[1200px] pt-8"
      >
        <div className="aspect-[4/3] animate-pulse rounded-lg bg-muted sm:aspect-[21/8]" />
        <div className="mt-8 h-12 w-2/3 animate-pulse rounded bg-muted" />
      </div>
    )
  }

  if (event.isError) {
    if (event.error instanceof ApiError && event.error.status === 404) {
      return <NotFound />
    }
    return (
      <div className="gutter mx-auto max-w-xl pt-16">
        <Notice tone="error">
          {event.error instanceof ApiError
            ? event.error.message
            : 'This event could not be loaded.'}{' '}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => void event.refetch()}
          >
            Try again
          </button>
        </Notice>
      </div>
    )
  }

  const item = event.data
  const refs = resolve(item)
  const { venue, category, home, away } = refs
  const league = item.league ? leagues.data?.get(item.league) : undefined
  const status = EVENT_STATUS[item.status]
  const blocker = bookingBlocker(item)
  const from = tiers.data ? lowestPrice(tiers.data) : null
  const seatsLink = `/events/${item.id}/seats`

  return (
    <article className="gutter mx-auto max-w-[1200px] pt-6 pb-24 lg:pb-0">
      <Link
        to="/events"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <HugeiconsIcon icon={ArrowLeft01Icon} size={16} aria-hidden />
        All events
      </Link>

      <EventMedia
        event={item}
        refs={refs}
        eager
        className="mt-4 aspect-[4/3] sm:aspect-[21/8]"
      />

      <div className="mt-8 grid gap-10 lg:mt-12 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-16">
        <div className="flex min-w-0 flex-col gap-10">
          <header className="flex flex-col gap-3">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm">
              <time
                dateTime={item.start_datetime}
                className="tabular font-medium text-ember-deep"
              >
                {formatDateTimeLong(item.start_datetime)}
              </time>
              {item.status !== 'approved' && (
                <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
              )}
            </div>
            <h1 className="font-display text-[clamp(2.75rem,7vw,4.5rem)] leading-[1] wrap-anywhere">
              {item.title}
            </h1>
            {isMatch && home && away && (
              <p className="text-lg">
                {home.name} <span className="text-muted-foreground">v</span>{' '}
                {away.name}
              </p>
            )}
            <p className="text-[15px] text-muted-foreground">
              {[category?.name, league?.name].filter(Boolean).join(', ')}
            </p>
          </header>

          {item.status === 'rejected' && item.rejection_reason && (
            <Notice tone="error">
              <strong className="font-semibold">Rejected:</strong>{' '}
              {item.rejection_reason}
            </Notice>
          )}

          <section className="grid gap-6 border-t border-border pt-8 sm:grid-cols-2">
            <div>
              <h2 className="text-sm font-medium">When</h2>
              <p className="mt-1 text-[15px] text-muted-foreground">
                <time dateTime={item.start_datetime}>
                  {formatDateTimeLong(item.start_datetime)}
                </time>
                <br />
                Ends{' '}
                <time dateTime={item.end_datetime}>
                  {formatDateTimeLong(item.end_datetime)}
                </time>
              </p>
            </div>
            {venue && (
              <div>
                <h2 className="text-sm font-medium">Where</h2>
                <p className="mt-1 text-[15px] text-muted-foreground">
                  {venue.name}
                  <br />
                  {venue.address}, {venue.city}, {venue.country}
                </p>
              </div>
            )}
          </section>

          {item.description && (
            <section className="border-t border-border pt-8">
              <h2 className="font-display text-[28px]">About this event</h2>
              {/* React escapes this text, so organizer-written descriptions can't inject HTML */}
              <p className="mt-3 max-w-[65ch] text-base leading-relaxed whitespace-pre-line">
                {item.description}
              </p>
            </section>
          )}
        </div>

        <div className="lg:sticky lg:top-24 lg:self-start">
          <TicketStub
            aria-label="Tickets"
            as="section"
            stub={
              blocker ? (
                <p className="text-sm text-muted-foreground">
                  {BLOCKER_MESSAGE[blocker]}
                </p>
              ) : (
                <div className="flex flex-col gap-3">
                  <ButtonLink size="lg" className="w-full" to={seatsLink}>
                    Choose seats
                  </ButtonLink>
                  <p className="text-center text-[13px] text-muted-foreground">
                    No booking fees. You pick exact seats next.
                  </p>
                </div>
              )
            }
          >
            <h2 className="text-lg font-semibold tracking-tight">Tickets</h2>
            {tiers.isPending ? (
              <p className="mt-3 text-sm text-muted-foreground">
                Loading prices…
              </p>
            ) : tiers.isError ? (
              <p className="mt-3 text-sm text-danger">
                Prices could not be loaded.
              </p>
            ) : tiers.data.length === 0 ? (
              <p className="mt-3 text-sm text-muted-foreground">
                Prices haven't been published yet.
              </p>
            ) : (
              <ul className="mt-3 flex flex-col">
                {tiers.data.map((tier) => (
                  <li
                    key={tier.id}
                    className="flex items-baseline justify-between gap-4 border-b border-border py-2.5 last:border-b-0"
                  >
                    <span className="text-[15px]">{tier.name}</span>
                    <span className="tabular font-semibold">
                      {formatMoney(tier.price)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </TicketStub>
        </div>
      </div>

      {/* Phones: the buy action stays in reach at the bottom of the screen */}
      {!blocker && (
        <div className="gutter fixed inset-x-0 bottom-0 z-20 flex items-center justify-between gap-4 border-t border-border bg-card/95 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur lg:hidden">
          <div className="text-sm">
            {from && (
              <>
                <span className="text-muted-foreground">From </span>
                <span className="tabular font-semibold">
                  {formatMoney(from)}
                </span>
              </>
            )}
          </div>
          <ButtonLink size="lg" to={seatsLink}>
            Choose seats
          </ButtonLink>
        </div>
      )}
    </article>
  )
}
