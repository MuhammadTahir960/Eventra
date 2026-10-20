import type { StatusTone } from '@/components/StatusBadge'
import type { EventItem, EventStatus } from './types'

export const EVENT_STATUS: Record<
  EventStatus,
  { label: string; tone: StatusTone }
> = {
  pending_approval: { label: 'Pending approval', tone: 'warning' },
  approved: { label: 'On sale', tone: 'success' },
  rejected: { label: 'Rejected', tone: 'danger' },
  cancelled: { label: 'Cancelled', tone: 'danger' },
  completed: { label: 'Ended', tone: 'neutral' },
}

export type BookingBlocker = 'not_seated' | 'not_on_sale' | 'started'

// Why seats can't be picked for this event, or null if they can.
// The backend enforces the same rules (hold returns 400/409), this just lets
// the page explain it up front instead of failing after a click.
export function bookingBlocker(event: EventItem): BookingBlocker | null {
  if (event.status !== 'approved') return 'not_on_sale'
  if (!event.is_seated) return 'not_seated'
  if (new Date(event.start_datetime).getTime() <= Date.now()) return 'started'
  return null
}

export const BLOCKER_MESSAGE: Record<BookingBlocker, string> = {
  not_on_sale: 'Tickets are not on sale for this event.',
  not_seated:
    'This event has no seat map yet, so tickets cannot be booked online.',
  started: 'This event has already started.',
}
