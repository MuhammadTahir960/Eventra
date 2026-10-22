import { useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { TicketStub } from '@/components/TicketStub'
import { ButtonLink } from '@/components/ui/button-link'
import { useEventLookups } from '@/features/events/lookups'
import { compareNatural } from '@/features/seating/layout/layout'
import type { EventItem } from '@/features/events/types'
import { formatDateTimeLong } from '@/lib/format'
import { cn } from '@/lib/utils'
import { TICKET_STATUS, useEventsById, useMyTickets, type Ticket } from '../api'
import { usePageTitle } from '@/lib/use-page-title'

type Tab = 'upcoming' | 'past'

interface Order {
  booking: string
  eventId: string
  title: string
  event: EventItem | undefined
  tickets: Ticket[]
}

// Tickets arrive flat; people think in orders: one event, several seats
function groupByOrder(
  tickets: Ticket[],
  events: Map<string, EventItem>,
): Order[] {
  const orders = new Map<string, Order>()
  for (const ticket of tickets) {
    const order = orders.get(ticket.booking) ?? {
      booking: ticket.booking,
      eventId: ticket.event_id,
      title: ticket.event_title,
      event: events.get(ticket.event_id),
      tickets: [],
    }
    order.tickets.push(ticket)
    orders.set(ticket.booking, order)
  }
  for (const order of orders.values()) {
    order.tickets.sort(
      (a, b) =>
        compareNatural(a.section, b.section) ||
        compareNatural(a.row_label, b.row_label) ||
        a.seat_number - b.seat_number,
    )
  }
  return [...orders.values()]
}

function isPast(order: Order): boolean {
  // The event couldn't be loaded (removed after a cancellation), so it is
  // over for the buyer: list it under Past, not in Upcoming forever
  if (!order.event) return true
  return (
    order.event.status === 'completed' ||
    new Date(order.event.end_datetime).getTime() < Date.now()
  )
}

export function MyTicketsPage() {
  usePageTitle('My tickets')
  const tickets = useMyTickets()
  const list = useMemo(() => tickets.data?.results ?? [], [tickets.data])
  const eventIds = useMemo(
    () => [...new Set(list.map((t) => t.event_id))],
    [list],
  )
  const events = useEventsById(eventIds)
  const { resolve } = useEventLookups([...events.byId.values()])
  // The tab is in the URL (?tab=past) so back and reload keep it
  const [params, setParams] = useSearchParams()
  const tab: Tab = params.get('tab') === 'past' ? 'past' : 'upcoming'
  const setTab = (next: Tab) =>
    setParams(next === 'past' ? { tab: 'past' } : {})

  const orders = useMemo(
    () => groupByOrder(list, events.byId),
    [list, events.byId],
  )
  const shown = orders
    .filter((order) => (tab === 'past' ? isPast(order) : !isPast(order)))
    .sort((a, b) => {
      const at = a.event ? new Date(a.event.start_datetime).getTime() : 0
      const bt = b.event ? new Date(b.event.start_datetime).getTime() : 0
      return tab === 'past' ? bt - at : at - bt
    })

  return (
    <div className="gutter mx-auto flex max-w-[960px] flex-col gap-8 pt-10 sm:pt-14">
      <PageHeader title="My tickets" />

      <div
        role="group"
        aria-label="Show tickets"
        className="inline-flex w-fit rounded-full border border-border bg-card p-1"
      >
        {(['upcoming', 'past'] as const).map((value) => (
          <button
            key={value}
            type="button"
            aria-pressed={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              'h-8 rounded-full px-4 text-sm transition-colors',
              tab === value
                ? 'bg-ink text-paper'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {value === 'upcoming' ? 'Upcoming' : 'Past'}
          </button>
        ))}
      </div>

      {tickets.isError ? (
        <Notice tone="error">
          {tickets.error.message}{' '}
          <button
            type="button"
            className="font-medium underline"
            onClick={() => void tickets.refetch()}
          >
            Try again
          </button>
        </Notice>
      ) : tickets.isPending || (eventIds.length > 0 && events.isPending) ? (
        <div
          aria-busy="true"
          aria-label="Loading tickets"
          className="flex flex-col gap-4"
        >
          {Array.from({ length: 2 }, (_, index) => (
            <div
              key={index}
              className="h-48 animate-pulse rounded-lg bg-muted"
            />
          ))}
        </div>
      ) : shown.length === 0 ? (
        <EmptyState
          title={tab === 'upcoming' ? 'No upcoming tickets' : 'No past tickets'}
          body={
            tab === 'upcoming'
              ? 'Tickets you buy show up here, ready to scan at the door.'
              : 'Events you have attended will be listed here.'
          }
          action={
            tab === 'upcoming' && (
              <ButtonLink to="/events">Find an event</ButtonLink>
            )
          }
        />
      ) : (
        <ul className="flex flex-col gap-5">
          {shown.map((order) => {
            const venue = order.event ? resolve(order.event).venue : undefined
            return (
              <li key={order.booking}>
                <TicketStub
                  as="article"
                  aria-label={order.title}
                  stub={
                    <ul className="flex flex-col">
                      {order.tickets.map((ticket) => {
                        const status = TICKET_STATUS[ticket.status]
                        return (
                          <li
                            key={ticket.id}
                            className="flex flex-wrap items-center justify-between gap-3 border-b border-border py-3 first:pt-0 last:border-b-0 last:pb-0"
                          >
                            <span className="min-w-0">
                              <span className="block font-medium">
                                {ticket.section}, row {ticket.row_label}, seat{' '}
                                {ticket.seat_number}
                              </span>
                              <span className="tabular block text-[13px] text-muted-foreground">
                                {ticket.ticket_code}
                              </span>
                            </span>
                            <span className="flex items-center gap-3">
                              <StatusBadge tone={status.tone}>
                                {status.label}
                              </StatusBadge>
                              <ButtonLink
                                variant="outline"
                                size="sm"
                                to={`/tickets/${ticket.id}`}
                              >
                                Show ticket
                              </ButtonLink>
                            </span>
                          </li>
                        )
                      })}
                    </ul>
                  }
                >
                  <div className="flex flex-col gap-1">
                    {order.event && (
                      <time
                        dateTime={order.event.start_datetime}
                        className="tabular text-[13px] font-medium text-ember-deep"
                      >
                        {formatDateTimeLong(order.event.start_datetime)}
                      </time>
                    )}
                    <h2 className="font-display text-[30px] leading-tight wrap-anywhere">
                      <Link
                        to={`/events/${order.eventId}`}
                        className="underline-offset-4 hover:underline"
                      >
                        {order.title}
                      </Link>
                    </h2>
                    {venue && (
                      <p className="text-sm text-muted-foreground">
                        {venue.name}, {venue.address}, {venue.city}
                      </p>
                    )}
                    {order.event?.status === 'cancelled' && (
                      <Notice tone="warning" className="mt-3">
                        This event was cancelled. Your payment is refunded to
                        the card you used.
                      </Notice>
                    )}
                  </div>
                </TicketStub>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
