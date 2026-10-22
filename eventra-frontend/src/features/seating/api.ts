import { apiFetch } from '@/lib/api-client'
import type { Booking, EventSeat, HoldResponse } from './types'

export const seatingApi = {
  // Public: the full seat map with each seat's current status
  getSeats: (eventId: string, signal?: AbortSignal) =>
    apiFetch<EventSeat[]>(`/events/${eventId}/seats/`, { signal }),

  // Reserves seats for 10 minutes. 409 means some were taken (the body names
  // them in `seat_ids`); 400 means a bad request such as more than 10 seats.
  holdSeats: (eventId: string, seatIds: string[]) =>
    apiFetch<HoldResponse>(`/events/${eventId}/seats/hold/`, {
      method: 'POST',
      body: { seat_ids: seatIds },
    }),

  // Turns a hold into a pending booking. Safe to repeat with the same hold id:
  // the backend returns the existing booking instead of creating another.
  createBooking: (holdId: string) =>
    apiFetch<Booking>('/bookings/', {
      method: 'POST',
      body: { hold_id: holdId },
    }),

  // Frees the signed-in user's unpaid booking for this event, so seats picked
  // before leaving checkout (back button or "Change seats") are released
  releaseMyBooking: (eventId: string) =>
    apiFetch<void>(`/events/${eventId}/seats/release/`, { method: 'POST' }),

  // Single-use, 30 second ticket for opening the seat WebSocket
  getSocketTicket: () =>
    apiFetch<{ ticket: string; expires_at: string }>('/auth/ws-ticket/', {
      method: 'POST',
    }),
}
