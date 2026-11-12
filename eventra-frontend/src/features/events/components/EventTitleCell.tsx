import { Link } from 'react-router-dom'
import { formatDateTime } from '@/lib/format'
import type { EventItem } from '../types'
import { PostponedFrom } from './PostponedFrom'

// `linked={false}` for deleted events, whose public page is a 404
export function EventTitleCell({
  event,
  linked = true,
}: {
  event: EventItem
  linked?: boolean
}) {
  return (
    <td className="min-w-64">
      {linked ? (
        <Link
          to={`/events/${event.id}`}
          className="font-medium underline-offset-4 hover:underline"
        >
          {event.title}
        </Link>
      ) : (
        <span className="font-medium">{event.title}</span>
      )}
      <span className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className="tabular text-[13px] text-muted-foreground">
          {formatDateTime(event.start_datetime)}
        </span>
        <PostponedFrom event={event} />
      </span>
    </td>
  )
}
