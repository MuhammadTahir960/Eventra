import type { EventSeat, SeatSocketMessage, SeatStatus } from './types'

const STATUSES: readonly string[] = ['available', 'held', 'booked']

function isSeat(value: unknown): value is EventSeat {
  if (typeof value !== 'object' || value === null) return false
  const seat = value as Record<string, unknown>
  return (
    typeof seat.id === 'string' &&
    typeof seat.section === 'string' &&
    typeof seat.row_label === 'string' &&
    typeof seat.seat_number === 'number' &&
    typeof seat.status === 'string' &&
    STATUSES.includes(seat.status)
  )
}

// Socket data is untrusted: accept only well-formed messages we know about
export function parseSeatMessage(raw: string): SeatSocketMessage | null {
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return null
  }
  if (typeof data !== 'object' || data === null) return null
  const message = data as Record<string, unknown>

  if (
    (message.type === 'initial_state' || message.type === 'seat_update') &&
    Array.isArray(message.seats) &&
    message.seats.every(isSeat)
  ) {
    return { type: message.type, seats: message.seats }
  }
  return null
}

// A full snapshot replaces everything (also what a reconnect sends);
// an update changes only the seats it names.
export function applySeatMessage(
  current: EventSeat[] | undefined,
  message: SeatSocketMessage,
): EventSeat[] | undefined {
  if (message.type === 'initial_state') return message.seats
  // An update without a base map means the REST load hasn't landed yet;
  // it will fetch the current state itself.
  if (!current) return current

  const changes = new Map(message.seats.map((seat) => [seat.id, seat]))
  return current.map((seat) => changes.get(seat.id) ?? seat)
}

// Seats from `selected` that someone else has taken in the meantime
export function takenFromSelection(
  seats: EventSeat[],
  selected: ReadonlySet<string>,
): EventSeat[] {
  const unavailable: SeatStatus[] = ['held', 'booked']
  return seats.filter(
    (seat) => selected.has(seat.id) && unavailable.includes(seat.status),
  )
}
