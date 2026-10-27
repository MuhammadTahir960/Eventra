import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowLeft01Icon, Cancel01Icon } from '@hugeicons/core-free-icons'
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { SwapLabel } from '@/components/SwapLabel'
import { TicketStub } from '@/components/TicketStub'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { saveCheckoutContext } from '@/features/bookings/api'
import { useEvent } from '@/features/events/hooks'
import { useEventLookups } from '@/features/events/lookups'
import { BLOCKER_MESSAGE, bookingBlocker } from '@/features/events/status'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, formatMoney } from '@/lib/format'
import { isUuid } from '@/lib/ids'
import { sumPrices } from '@/lib/money'
import { cn } from '@/lib/utils'
import { seatingApi } from '../api'
import { SeatMap } from '../components/SeatMap'
import { useLiveSeats, type ConnectionState } from '../hooks'
import { compareNatural } from '../layout/layout'
import { takenFromSelection } from '../seat-state'
import { MAX_SEATS_PER_HOLD, type EventSeat } from '../types'
import { usePageTitle } from '@/lib/use-page-title'

const CONNECTION_TEXT: Record<ConnectionState, string> = {
  connecting: 'Connecting',
  live: 'Live',
  reconnecting: 'Reconnecting',
  polling: 'Updates every 15 seconds',
}

function ConnectionPill({ state }: { state: ConnectionState }) {
  return (
    <span
      role="status"
      className="inline-flex h-7 w-fit items-center gap-2 rounded-full border border-border bg-card px-3 text-[13px] text-muted-foreground"
    >
      <span
        aria-hidden
        className={cn(
          'size-2 rounded-full',
          state === 'live' ? 'bg-success' : 'bg-warning-mark',
          state !== 'live' && state !== 'polling' && 'animate-pulse',
        )}
      />
      {CONNECTION_TEXT[state]}
    </span>
  )
}

function seatLabel(seat: EventSeat) {
  return `${seat.section}, row ${seat.row_label}, seat ${seat.seat_number}`
}

function bySeatOrder(a: EventSeat, b: EventSeat) {
  return (
    compareNatural(a.section, b.section) ||
    compareNatural(a.row_label, b.row_label) ||
    a.seat_number - b.seat_number
  )
}

export function SeatsPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const event = useEvent(id)
  usePageTitle(
    event.data ? `Choose seats: ${event.data.title}` : 'Choose seats',
  )
  const { resolve } = useEventLookups(event.data ? [event.data] : undefined)
  // No live socket when nothing can be booked: ticket holders on an event under
  // review can't open its seat feed, so it would only retry and then poll a 404
  const liveSlug =
    event.data && !bookingBlocker(event.data) ? event.data.slug : undefined
  const { seats, connection } = useLiveSeats(id, liveSlug)

  const [selected, setSelected] = useState<ReadonlySet<string>>(new Set())
  const [message, setMessage] = useState<{
    tone: 'error' | 'warning'
    text: string
  } | null>(null)
  const [pending, setPending] = useState(false)

  const allSeats = useMemo(() => seats.data ?? [], [seats.data])

  // Arriving here from checkout means the user changed their mind: free the
  // seats they were about to pay for. Best effort; the next hold and the
  // expiry sweep release them too.
  const { refetch } = seats
  useEffect(() => {
    if (!isUuid(id)) return
    seatingApi
      .releaseMyBooking(id)
      .then(() => refetch())
      .catch(() => {})
  }, [id, refetch])

  // Someone else took a seat in the cart: drop it and say which
  useEffect(() => {
    const taken = takenFromSelection(allSeats, selected)
    if (taken.length === 0) return
    setSelected((current) => {
      const next = new Set(current)
      for (const seat of taken) next.delete(seat.id)
      return next
    })
    setMessage({
      tone: 'warning',
      text: `${taken.map(seatLabel).join('; ')} ${taken.length === 1 ? 'was' : 'were'} just taken by someone else and removed from your selection.`,
    })
  }, [allSeats, selected])

  const cart = useMemo(
    () => allSeats.filter((seat) => selected.has(seat.id)).sort(bySeatOrder),
    [allSeats, selected],
  )
  const total = sumPrices(cart.map((seat) => seat.price))

  function toggle(seatId: string) {
    if (!selected.has(seatId) && selected.size >= MAX_SEATS_PER_HOLD) {
      setMessage({
        tone: 'warning',
        text: `You can book up to ${MAX_SEATS_PER_HOLD} seats at a time.`,
      })
      return
    }
    setMessage(null)
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(seatId)) next.delete(seatId)
      else next.add(seatId)
      return next
    })
  }

  async function checkout() {
    if (!event.data || cart.length === 0) return
    setPending(true)
    setMessage(null)
    try {
      // Shopping-cart model: hold and book on the same click
      const hold = await seatingApi.holdSeats(
        event.data.id,
        cart.map((seat) => seat.id),
      )
      const booking = await seatingApi.createBooking(hold.hold_id)
      const context = {
        eventId: event.data.id,
        eventTitle: event.data.title,
        seats: hold.seats,
      }
      saveCheckoutContext(booking.id, context)
      navigate(`/checkout/${booking.id}`, { state: context })
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 409) {
        // The body names seats someone else holds or bought
        const ids = (caught.data as { seat_ids?: unknown } | undefined)
          ?.seat_ids
        if (Array.isArray(ids) && ids.length > 0) {
          setSelected((current) => {
            const next = new Set(current)
            for (const seatId of ids) next.delete(String(seatId))
            return next
          })
          void seats.refetch()
          setMessage({
            tone: 'warning',
            text: 'Some of those seats were taken a moment ago and have been removed. Check your selection and try again.',
          })
        } else {
          setMessage({ tone: 'error', text: caught.message })
        }
      } else {
        setMessage({
          tone: 'error',
          text:
            caught instanceof ApiError
              ? caught.message
              : 'Checkout could not start. Please try again.',
        })
      }
      setPending(false)
    }
  }

  if (
    !isUuid(id) ||
    (event.isError &&
      event.error instanceof ApiError &&
      event.error.status === 404)
  ) {
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

  if (event.isPending) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading seats"
        className="gutter mx-auto max-w-[1200px] pt-10"
      >
        <div className="h-12 w-1/2 animate-pulse rounded bg-muted" />
        <div className="mt-8 aspect-[16/10] animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (event.isError) {
    return (
      <div className="gutter mx-auto max-w-xl pt-16">
        <Notice tone="error">{event.error.message}</Notice>
      </div>
    )
  }

  const item = event.data
  const { venue } = resolve(item)
  const blocker = bookingBlocker(item)
  const fieldLabel = item.event_type === 'sports_match' ? 'Pitch' : 'Stage'

  return (
    <div className="gutter mx-auto max-w-[1200px] pt-6 pb-28 lg:pb-0">
      <Link
        to={`/events/${item.id}`}
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <HugeiconsIcon icon={ArrowLeft01Icon} size={16} aria-hidden />
        Event details
      </Link>

      <header className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-col gap-1.5">
          <h1 className="font-display text-[clamp(2.25rem,5vw,3.25rem)] leading-[1.05]">
            Choose your seats
          </h1>
          <p className="text-[15px] text-muted-foreground">
            {item.title}
            <br />
            <time dateTime={item.start_datetime} className="tabular">
              {formatDateTime(item.start_datetime)}
            </time>
            {venue && `, ${venue.name}`}
          </p>
        </div>
        {!blocker && <ConnectionPill state={connection} />}
      </header>

      {blocker ? (
        <Notice className="mt-8">{BLOCKER_MESSAGE[blocker]}</Notice>
      ) : (
        <div className="mt-8 grid gap-8 lg:grid-cols-[minmax(0,1fr)_340px]">
          <section aria-label="Seat map" className="min-w-0">
            {seats.isPending ? (
              <div
                aria-busy="true"
                className="aspect-[16/10] animate-pulse rounded-lg bg-muted"
              />
            ) : seats.isError ? (
              <Notice tone="error">
                The seat map could not be loaded.{' '}
                <button
                  type="button"
                  className="font-medium underline"
                  onClick={() => void seats.refetch()}
                >
                  Try again
                </button>
              </Notice>
            ) : allSeats.length === 0 ? (
              <Notice>This event has no seats on sale.</Notice>
            ) : (
              <SeatMap
                seats={allSeats}
                shape={venue?.layout_shape ?? 'oval'}
                selected={selected}
                onToggle={toggle}
                disabled={pending}
                fieldLabel={fieldLabel}
              />
            )}
          </section>

          <aside className="lg:sticky lg:top-24 lg:self-start">
            <TicketStub
              as="section"
              aria-label="Your selection"
              stub={
                <div className="flex flex-col gap-4">
                  <div className="flex items-baseline justify-between">
                    <span className="font-medium">Total</span>
                    <span className="tabular text-xl font-semibold">
                      {formatMoney(total)}
                    </span>
                  </div>
                  <Button
                    size="lg"
                    className="w-full"
                    disabled={cart.length === 0 || pending}
                    onClick={() => void checkout()}
                  >
                    <SwapLabel>
                      {pending ? 'Reserving seats…' : 'Continue to payment'}
                    </SwapLabel>
                  </Button>
                  <p className="text-[13px] text-muted-foreground">
                    No booking fees. Your seats are held for you while you pay.
                  </p>
                </div>
              }
            >
              <div className="flex items-baseline justify-between">
                <h2 className="text-lg font-semibold tracking-tight">
                  Your selection
                </h2>
                <span className="tabular text-[13px] text-muted-foreground">
                  {cart.length} of {MAX_SEATS_PER_HOLD}
                </span>
              </div>

              {message && (
                <Notice tone={message.tone} className="mt-4">
                  {message.text}
                </Notice>
              )}

              {cart.length === 0 ? (
                <p className="mt-4 text-sm text-muted-foreground">
                  Tap open seats on the map to add them here.
                </p>
              ) : (
                <ul className="mt-3 flex flex-col">
                  {cart.map((seat) => (
                    <li
                      key={seat.id}
                      className="flex items-center gap-3 border-b border-border py-2.5 transition-[opacity,translate] duration-200 ease-out last:border-b-0 starting:-translate-y-1 starting:opacity-0 motion-reduce:starting:translate-y-0"
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block text-sm font-medium">
                          {seat.section}, row {seat.row_label}, seat{' '}
                          {seat.seat_number}
                        </span>
                        <span className="block text-[13px] text-muted-foreground">
                          {seat.tier_name}
                        </span>
                      </span>
                      <span className="tabular text-sm font-medium">
                        {formatMoney(seat.price)}
                      </span>
                      <button
                        type="button"
                        onClick={() => toggle(seat.id)}
                        disabled={pending}
                        aria-label={`Remove ${seatLabel(seat)}`}
                        className="grid size-8 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
                      >
                        <HugeiconsIcon icon={Cancel01Icon} size={16} />
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </TicketStub>
          </aside>
        </div>
      )}

      {/* Phones: total and checkout stay in reach below the map */}
      {!blocker && (
        <div className="gutter fixed inset-x-0 bottom-0 z-20 flex items-center justify-between gap-4 border-t border-border bg-card/95 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] backdrop-blur lg:hidden">
          <div className="text-sm">
            <span className="block text-muted-foreground">
              {cart.length} {cart.length === 1 ? 'seat' : 'seats'}
            </span>
            <span className="tabular font-semibold">{formatMoney(total)}</span>
          </div>
          <Button
            size="lg"
            disabled={cart.length === 0 || pending}
            onClick={() => void checkout()}
          >
            <SwapLabel>{pending ? 'Reserving…' : 'Continue'}</SwapLabel>
          </Button>
        </div>
      )}
    </div>
  )
}
