export type SeatStatus = 'available' | 'held' | 'booked'

// Shape of the backend's EventSeatSerializer (REST and WebSocket alike).
// It is a superset of the layout engine's seat input.
export interface EventSeat {
  id: string
  section: string
  row_label: string
  seat_number: number
  ticket_tier: string
  tier_name: string
  // A JSON number from this endpoint (45.0), unlike the decimal strings
  // elsewhere; only use it through lib/money and formatMoney
  price: string | number
  status: SeatStatus
}

// POST /events/{id}/seats/hold/
export interface HoldResponse {
  // Shared id of the held group; this is what POST /bookings/ takes
  hold_id: string
  expires_at: string
  seats: EventSeat[]
}

// POST /bookings/. The booking carries no event or seat details, so the
// caller keeps those itself (they are passed along to checkout).
export interface Booking {
  id: string
  status: 'pending' | 'confirmed' | 'cancelled' | 'refunded' | 'refund_failed'
  total_amount: string
  source_hold_group_id: string
  created_at: string
  updated_at: string
}

// Messages sent over /ws/seats/{slug}/ (read-only for the client)
export type SeatSocketMessage =
  | { type: 'initial_state'; seats: EventSeat[] }
  | { type: 'seat_update'; seats: EventSeat[] }

// Limits enforced by the backend (apps/seating/constants.py)
export const MAX_SEATS_PER_HOLD = 10
