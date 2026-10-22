import {
  Elements,
  PaymentElement,
  useElements,
  useStripe,
} from '@stripe/react-stripe-js'
import { loadStripe, type Appearance, type Stripe } from '@stripe/stripe-js'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { SwapLabel } from '@/components/SwapLabel'
import { TicketStub } from '@/components/TicketStub'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { ApiError } from '@/lib/api-client'
import { formatMoney } from '@/lib/format'
import { isUuid } from '@/lib/ids'
import { ReceiptPrinter, type PrinterStage } from '../components/ReceiptPrinter'
import {
  bookingDeadline,
  loadCheckoutContext,
  type CheckoutContext,
} from '../api'
import {
  CONFIRM_GIVE_UP_MS,
  formatCountdown,
  useBooking,
  useCheckout,
  useTimeLeft,
} from '../hooks'
import { usePageTitle } from '@/lib/use-page-title'

const clockFormat = new Intl.DateTimeFormat(undefined, {
  hour: 'numeric',
  minute: '2-digit',
})

// Stripe's form drawn in the brand's tokens (it renders in its own iframe,
// so CSS variables don't reach it and the values are repeated here)
const APPEARANCE: Appearance = {
  theme: 'stripe',
  variables: {
    colorPrimary: '#c9431f',
    colorBackground: '#ffffff',
    colorText: '#141413',
    colorTextSecondary: '#6b6a65',
    colorDanger: '#b4233c',
    fontFamily: 'Geist, ui-sans-serif, system-ui, sans-serif',
    fontSizeBase: '15px',
    borderRadius: '8px',
    spacingUnit: '4px',
  },
  rules: {
    '.Input': { borderColor: '#cfcbc0', boxShadow: 'none' },
    '.Input:focus': {
      borderColor: '#c9431f',
      boxShadow: '0 0 0 3px rgb(201 67 31 / 0.15)',
    },
    '.Label': { fontWeight: '500', color: '#141413' },
  },
}
const FONTS = [
  {
    cssSrc:
      'https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap',
  },
]

// One Stripe.js instance per publishable key
const stripeByKey = new Map<string, Promise<Stripe | null>>()
function stripeFor(key: string) {
  if (!stripeByKey.has(key)) stripeByKey.set(key, loadStripe(key))
  return stripeByKey.get(key)!
}

// Payments run in Stripe test mode, which declines real cards
function TestCardHint() {
  return (
    <p className="text-sm text-muted-foreground">
      Payments are in test mode. Use card{' '}
      <span className="tabular font-medium whitespace-nowrap text-foreground">
        4242 4242 4242 4242
      </span>{' '}
      with any future date and any CVC.
    </p>
  )
}

function PaymentForm({
  bookingId,
  amount,
  expired,
  onPaid,
}: {
  bookingId: string
  amount: string
  expired: boolean
  onPaid: () => void
}) {
  const stripe = useStripe()
  const elements = useElements()
  const [error, setError] = useState<string | null>(null)
  const [paying, setPaying] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!stripe || !elements) return
    setPaying(true)
    setError(null)
    const result = await stripe.confirmPayment({
      elements,
      // Only used when a card needs a redirect (3-D Secure)
      confirmParams: {
        return_url: `${window.location.origin}/checkout/${bookingId}`,
      },
      redirect: 'if_required',
    })
    if (result.error) {
      setError(result.error.message ?? 'The payment could not be completed.')
      setPaying(false)
      return
    }
    onPaid()
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-5">
      <PaymentElement options={{ layout: 'tabs' }} />
      {error && <Notice tone="error">{error}</Notice>}
      <Button
        type="submit"
        size="lg"
        className="w-full"
        disabled={!stripe || paying || expired}
      >
        <SwapLabel>
          {paying ? 'Processing payment…' : `Pay ${formatMoney(amount)}`}
        </SwapLabel>
      </Button>
    </form>
  )
}

function OrderSummary({
  context,
  total,
}: {
  context: CheckoutContext | null
  total: string
}) {
  return (
    <TicketStub
      as="section"
      aria-label="Order summary"
      stub={
        <div className="flex items-baseline justify-between">
          <span className="font-medium">Total</span>
          <span className="tabular text-xl font-semibold">
            {formatMoney(total)}
          </span>
        </div>
      }
    >
      <h2 className="text-lg font-semibold tracking-tight">Order summary</h2>
      {context ? (
        <>
          <p className="mt-1 text-[15px]">{context.eventTitle}</p>
          <ul className="mt-3 flex flex-col">
            {context.seats.map((seat) => (
              <li
                key={seat.id}
                className="flex justify-between gap-4 border-b border-border py-2 text-sm last:border-b-0"
              >
                <span>
                  {seat.section}, row {seat.row_label}, seat {seat.seat_number}
                  <span className="block text-[13px] text-muted-foreground">
                    {seat.tier_name}
                  </span>
                </span>
                <span className="tabular font-medium">
                  {formatMoney(seat.price)}
                </span>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p className="mt-1 text-sm text-muted-foreground">
          Your reserved seats
        </p>
      )}
      <div className="mt-3 flex justify-between text-sm text-muted-foreground">
        <span>Booking fees</span>
        <span>None</span>
      </div>
    </TicketStub>
  )
}

export function CheckoutPage() {
  usePageTitle('Checkout')
  const { bookingId } = useParams()
  const location = useLocation()
  const [params] = useSearchParams()
  // Stripe's 3-D Secure redirect comes back with redirect_status in the URL
  const [paidAt, setPaidAt] = useState<number | null>(() =>
    params.get('redirect_status') === 'succeeded' ? Date.now() : null,
  )
  const paid = paidAt !== null
  // Set when the receipt has finished feeding out
  const [printed, setPrinted] = useState(false)

  const context = useMemo<CheckoutContext | null>(
    () =>
      (location.state as CheckoutContext | null) ??
      (bookingId ? loadCheckoutContext(bookingId) : null),
    [location.state, bookingId],
  )

  const booking = useBooking(bookingId, paidAt)
  const isPending = booking.data?.status === 'pending'
  const deadline = useMemo(
    () => (booking.data && isPending ? bookingDeadline(booking.data) : null),
    [booking.data, isPending],
  )
  const timeLeft = useTimeLeft(deadline)
  // Matches how long useBooking keeps polling for the webhook
  const confirmWindow = useMemo(
    () => (paidAt ? new Date(paidAt + CONFIRM_GIVE_UP_MS) : null),
    [paidAt],
  )
  const stillConfirming = useTimeLeft(confirmWindow) > 0
  const expired = Boolean(deadline) && timeLeft === 0 && !paid
  const checkout = useCheckout(bookingId, isPending && !paid && !expired)

  if (
    !isUuid(bookingId) ||
    (booking.error instanceof ApiError && booking.error.status === 404)
  ) {
    return (
      <div className="gutter mx-auto max-w-[1200px] pt-16">
        <EmptyState
          title="Booking not found"
          body="The link may be wrong, or the booking belongs to another account."
          action={
            <ButtonLink variant="ink" to="/events">
              Browse events
            </ButtonLink>
          }
        />
      </div>
    )
  }

  if (booking.isPending) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading checkout"
        className="gutter mx-auto max-w-[1100px] pt-10"
      >
        <div className="h-12 w-1/3 animate-pulse rounded bg-muted" />
        <div className="mt-8 h-80 animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (booking.isError) {
    return (
      <div className="gutter mx-auto max-w-xl pt-16">
        <Notice tone="error">{booking.error.message}</Notice>
      </div>
    )
  }

  const order = booking.data
  const seatsLink = context ? `/events/${context.eventId}/seats` : '/events'

  // Paid: the printer shows "confirming" until the webhook lands, then feeds
  // the receipt out. A confirmed booking opened later shows it already printed.
  if (order.status === 'confirmed' || (paid && isPending)) {
    const confirmed = order.status === 'confirmed'
    const stalled = !confirmed && !stillConfirming
    const stage: PrinterStage = !confirmed
      ? 'processing'
      : paid && !printed
        ? 'printing'
        : 'complete'
    return (
      <div className="gutter mx-auto flex max-w-[640px] flex-col gap-8 pt-12">
        <PageHeader
          title={
            stage === 'processing'
              ? 'Confirming your payment'
              : stage === 'printing'
                ? 'Payment confirmed'
                : "You're going"
          }
          description={
            stalled
              ? "Your payment went through. Your tickets will appear in My tickets as soon as it's confirmed."
              : stage === 'processing'
                ? 'This usually takes a few seconds. Please keep this page open.'
                : 'Your tickets are ready, and a copy is on its way to your email.'
          }
        />
        <ReceiptPrinter
          stage={stage}
          stalled={stalled}
          eventTitle={context?.eventTitle ?? null}
          seats={context?.seats ?? []}
          total={order.total_amount}
          orderId={order.id}
          paidAt={new Date(paidAt ?? order.updated_at)}
          onPrinted={() => setPrinted(true)}
        />
        {(stage === 'complete' || stalled) && (
          <div className="flex flex-wrap justify-center gap-3 transition-opacity duration-200 ease-out starting:opacity-0">
            <ButtonLink variant="ink" size="lg" to="/bookings">
              View my tickets
            </ButtonLink>
            <ButtonLink variant="ghost" size="lg" to="/events">
              Find more events
            </ButtonLink>
          </div>
        )}
      </div>
    )
  }

  if (!isPending) {
    return (
      <div className="gutter mx-auto max-w-[640px] pt-16">
        <EmptyState
          title="This booking is closed"
          body="It was cancelled or refunded, so it can't be paid for."
          action={
            <ButtonLink variant="ink" to="/bookings">
              View my tickets
            </ButtonLink>
          }
        />
      </div>
    )
  }

  const key = checkout.data?.publishable_key ?? ''
  // The project never takes real payments: refuse anything but a test key
  const keyIsTest = key.startsWith('pk_test_')

  return (
    <div className="gutter mx-auto max-w-[1100px] pt-8">
      <Link
        to={seatsLink}
        className="text-sm text-muted-foreground hover:text-foreground"
      >
        Change seats
      </Link>
      <PageHeader className="mt-4" title="Checkout" size="md" />

      <div className="mt-8 grid gap-10 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section aria-label="Payment" className="flex min-w-0 flex-col gap-5">
          {expired ? (
            <EmptyState
              title="Your hold has ended"
              body="The seats were released so others can book them. Pick seats again to start a new booking."
              action={
                <ButtonLink to={seatsLink}>Choose seats again</ButtonLink>
              }
            />
          ) : (
            <>
              {deadline && (
                <p role="timer" aria-live="off" className="text-[15px]">
                  Seats held until{' '}
                  <strong className="tabular font-semibold">
                    {clockFormat.format(deadline)}
                  </strong>{' '}
                  <span className="tabular text-muted-foreground">
                    ({formatCountdown(timeLeft)} left)
                  </span>
                </p>
              )}
              <TestCardHint />
              {checkout.isPending ? (
                <div
                  aria-busy="true"
                  aria-label="Loading payment form"
                  className="h-64 animate-pulse rounded-lg bg-muted"
                />
              ) : checkout.isError ? (
                <Notice tone="error">
                  {checkout.error instanceof ApiError
                    ? checkout.error.message
                    : 'The payment form could not be loaded.'}{' '}
                  <button
                    type="button"
                    className="font-medium underline"
                    onClick={() => void checkout.refetch()}
                  >
                    Try again
                  </button>
                </Notice>
              ) : !keyIsTest ? (
                <Notice tone="error">
                  Payments are unavailable right now. Please try again later.
                </Notice>
              ) : (
                <div className="rounded-lg border border-border bg-card p-5 sm:p-6">
                  <Elements
                    stripe={stripeFor(key)}
                    options={{
                      clientSecret: checkout.data.client_secret,
                      appearance: APPEARANCE,
                      fonts: FONTS,
                    }}
                  >
                    <PaymentForm
                      bookingId={order.id}
                      amount={order.total_amount}
                      expired={expired}
                      onPaid={() => setPaidAt(Date.now())}
                    />
                  </Elements>
                </div>
              )}
            </>
          )}
        </section>

        <aside className="lg:sticky lg:top-24 lg:self-start">
          <OrderSummary context={context} total={order.total_amount} />
        </aside>
      </div>
    </div>
  )
}
