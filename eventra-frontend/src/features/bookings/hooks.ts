import { useQuery } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { isUuid } from '@/lib/ids'
import { bookingsApi } from './api'

// How long checkout waits for the Stripe webhook to confirm a payment
const CONFIRM_POLL_MS = 2_000
export const CONFIRM_GIVE_UP_MS = 60_000

// `paidAt` is when the buyer paid (ms), or null while they haven't yet
export function useBooking(id: string | undefined, paidAt: number | null) {
  return useQuery({
    queryKey: ['bookings', 'detail', id],
    queryFn: ({ signal }) => bookingsApi.get(id ?? '', signal),
    enabled: isUuid(id),
    retry: false,
    // After paying, poll until the webhook marks the booking confirmed
    refetchInterval: (query) =>
      paidAt !== null &&
      query.state.data?.status === 'pending' &&
      Date.now() - paidAt < CONFIRM_GIVE_UP_MS
        ? CONFIRM_POLL_MS
        : false,
  })
}

// Starts (or refreshes) the PaymentIntent once per booking. Not refetched on
// focus: each call may touch Stripe, and the client secret stays valid.
export function useCheckout(id: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ['bookings', 'checkout', id],
    queryFn: () => bookingsApi.checkout(id ?? ''),
    enabled: enabled && isUuid(id),
    staleTime: Infinity,
    gcTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  })
}

// Milliseconds left until `deadline`, updated every second; 0 once passed
export function useTimeLeft(deadline: Date | null): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!deadline) return
    const timer = setInterval(() => setNow(Date.now()), 1_000)
    return () => clearInterval(timer)
  }, [deadline])
  return deadline ? Math.max(0, deadline.getTime() - now) : 0
}

export function formatCountdown(ms: number): string {
  const total = Math.ceil(ms / 1_000)
  const minutes = Math.floor(total / 60)
  const seconds = String(total % 60).padStart(2, '0')
  return `${minutes}:${seconds}`
}
