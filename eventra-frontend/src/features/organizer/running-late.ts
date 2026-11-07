import type { EventItem } from '@/features/events/types'
import { DAY_MS } from '@/lib/constants'

// "Running late" is offered from a day before the start until the event
// completes: delayed starts, overruns and matches resumed the next day
export function canRunLate(event: EventItem, now = Date.now()): boolean {
  return (
    (event.status === 'approved' || event.status === 'pending_approval') &&
    now >= new Date(event.start_datetime).getTime() - DAY_MS
  )
}

// Postponing is offered until the event starts
export function canPostpone(event: EventItem, now = Date.now()): boolean {
  return (
    (event.status === 'approved' || event.status === 'pending_approval') &&
    now < new Date(event.start_datetime).getTime()
  )
}
