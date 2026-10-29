import type { EventItem } from '@/features/events/types'

// "Running late" is offered from a day before the start until the event
// completes: delayed starts, overruns and matches resumed the next day
export function canRunLate(event: EventItem, now = Date.now()): boolean {
  return (
    (event.status === 'approved' || event.status === 'pending_approval') &&
    now >= new Date(event.start_datetime).getTime() - 24 * 60 * 60 * 1000
  )
}
