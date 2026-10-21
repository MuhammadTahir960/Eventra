import { apiFetch } from '@/lib/api-client'
import type { Booking, EventSeat } from '@/features/seating/types'

// POST /bookings/{id}/checkout/ (creates or refreshes the PaymentIntent)
export interface CheckoutResponse {
  client_secret: string
  publishable_key: string
  // Whole cents (Stripe's unit), not dollars: display the booking's
  // total_amount instead
  amount: number
  currency: string
  status: string
}

export const bookingsApi = {
  get: (id: string, signal?: AbortSignal) =>
    apiFetch<Booking>(`/bookings/${id}/`, { signal }),

  checkout: (id: string) =>
    apiFetch<CheckoutResponse>(`/bookings/${id}/checkout/`, {
      method: 'POST',
    }),
}

// Pending bookings expire this long after they're created
// (BOOKING_EXPIRY_MINUTES in the backend's bookings/services.py)
export const BOOKING_EXPIRY_MS = 5 * 60_000

export function bookingDeadline(booking: Pick<Booking, 'created_at'>): Date {
  return new Date(new Date(booking.created_at).getTime() + BOOKING_EXPIRY_MS)
}

// The booking API returns no event or seat details, so the seat page hands
// them to checkout. Kept in sessionStorage too, so a reload keeps the summary.
export interface CheckoutContext {
  eventId: string
  eventTitle: string
  seats: EventSeat[]
}

const contextKey = (bookingId: string) => `eventra-checkout-${bookingId}`

export function saveCheckoutContext(
  bookingId: string,
  context: CheckoutContext,
) {
  try {
    sessionStorage.setItem(contextKey(bookingId), JSON.stringify(context))
  } catch {
    // Storage blocked: the summary just won't survive a reload
  }
}

export function loadCheckoutContext(bookingId: string): CheckoutContext | null {
  try {
    const raw = sessionStorage.getItem(contextKey(bookingId))
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    // Our own data, but storage is editable: check the shape before use
    if (
      parsed &&
      typeof parsed === 'object' &&
      typeof (parsed as CheckoutContext).eventId === 'string' &&
      typeof (parsed as CheckoutContext).eventTitle === 'string' &&
      Array.isArray((parsed as CheckoutContext).seats)
    ) {
      return parsed as CheckoutContext
    }
  } catch {
    // Unreadable or blocked storage
  }
  return null
}
