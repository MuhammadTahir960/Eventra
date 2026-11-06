import { StatusBadge } from '@/components/StatusBadge'
import { formatDateTime } from '@/lib/format'
import type { EventItem } from '../types'

// Next to the start date: the event moved, and from when
export function PostponedFrom({
  event,
}: {
  event: Pick<EventItem, 'postponed_from'>
}) {
  if (!event.postponed_from) return null
  return (
    <>
      <StatusBadge tone="warning">Postponed</StatusBadge>
      <span className="text-[13px] text-muted-foreground">
        Was{' '}
        <del>
          <time dateTime={event.postponed_from}>
            {formatDateTime(event.postponed_from)}
          </time>
        </del>
      </span>
    </>
  )
}
