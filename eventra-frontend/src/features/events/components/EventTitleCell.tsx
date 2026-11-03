import { Link } from 'react-router-dom'
import { formatDateTime } from '@/lib/format'
import type { EventItem } from '../types'
import { PostponedFrom } from './PostponedFrom'

export function EventTitleCell({ event }: { event: EventItem }) {
  return (
    <td className="min-w-64">
      <Link
        to={`/events/${event.id}`}
        className="font-medium underline-offset-4 hover:underline"
      >
        {event.title}
      </Link>
      <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="tabular text-[13px] text-muted-foreground">
          {formatDateTime(event.start_datetime)}
        </span>
        <PostponedFrom event={event} />
      </span>
    </td>
  )
}
