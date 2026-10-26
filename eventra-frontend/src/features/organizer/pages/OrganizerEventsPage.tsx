import { useState } from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { HoldToConfirmButton } from '@/components/HoldToConfirmButton'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { useEventLookups } from '@/features/events/lookups'
import { EVENT_STATUS } from '@/features/events/status'
import type { EventItem } from '@/features/events/types'
import { ApiError } from '@/lib/api-client'
import { formatDateTime } from '@/lib/format'
import { useCancelEvent, useOrganizerEvents } from '../api'
import { usePageTitle } from '@/lib/use-page-title'

const TERMINAL: EventItem['status'][] = ['cancelled', 'completed']

// Cancelling refunds every buyer, so it always goes through a confirmation
export function CancelEventButton({
  event,
  size = 'sm',
}: {
  event: EventItem
  size?: 'sm' | 'default'
}) {
  const [open, setOpen] = useState(false)
  const cancel = useCancelEvent()
  const [error, setError] = useState<string | null>(null)
  // Bumped after a failure so the hold button re-arms
  const [attempt, setAttempt] = useState(0)
  const hintId = `cancel-hint-${event.id}`

  function confirm() {
    cancel.mutate(event.id, {
      onSuccess: () => {
        setOpen(false)
        toast.success('Event cancelled', {
          description: 'Every buyer is being refunded in full.',
        })
      },
      onError: (caught) => {
        setError(
          caught instanceof ApiError
            ? caught.message
            : 'The event could not be cancelled.',
        )
        setAttempt((n) => n + 1)
      },
    })
  }

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) setError(null)
      }}
      trigger={
        <Button variant="destructive" size={size}>
          Cancel
        </Button>
      }
      title="Cancel this event?"
      description={
        <>
          <strong className="font-medium text-foreground">{event.title}</strong>{' '}
          will be taken off sale and every buyer is refunded in full. This can't
          be undone.
        </>
      }
      confirmLabel="Cancel event"
      destructive
      pending={cancel.isPending}
      onConfirm={confirm}
      // Refunding every buyer is the most destructive action in the app, so
      // it takes a deliberate hold rather than one click
      confirmControl={
        <HoldToConfirmButton
          key={attempt}
          label="Hold to cancel event"
          confirmedLabel="Cancelling…"
          hintId={hintId}
          disabled={cancel.isPending}
          onConfirm={confirm}
        />
      }
    >
      <p id={hintId} className="text-[13px] text-muted-foreground">
        Press and hold the button until it fills to confirm.
      </p>
      {error && (
        <Notice tone="error" className="mt-3">
          {error}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

export function OrganizerEventsPage() {
  usePageTitle('My events')
  const events = useOrganizerEvents()
  const list = events.data?.results ?? []
  const { resolve } = useEventLookups(list)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="My events"
        description="Every event you've listed, newest first. Edits to dates, venue or category go back to an admin for approval."
        actions={
          <ButtonLink variant="ink" to="/organizer/events/new">
            Create event
          </ButtonLink>
        }
      />

      {events.isError ? (
        <Notice tone="error">{events.error.message}</Notice>
      ) : events.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading events"
          className="h-64 animate-pulse rounded-lg bg-muted"
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No events yet"
          body="Create your first event. An admin reviews it before it goes on sale."
          action={
            <ButtonLink variant="ink" to="/organizer/events/new">
              Create event
            </ButtonLink>
          }
        />
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Event</th>
                <th scope="col">Venue</th>
                <th scope="col">Status</th>
                <th scope="col">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {list.map((event) => {
                const status = EVENT_STATUS[event.status]
                const { venue } = resolve(event)
                const terminal = TERMINAL.includes(event.status)
                return (
                  <tr key={event.id}>
                    <td className="min-w-64">
                      <Link
                        to={`/events/${event.id}`}
                        className="font-medium underline-offset-4 hover:underline"
                      >
                        {event.title}
                      </Link>
                      <span className="tabular block text-[13px] text-muted-foreground">
                        {formatDateTime(event.start_datetime)}
                      </span>
                    </td>
                    <td className="text-muted-foreground">
                      {venue ? `${venue.name}, ${venue.city}` : ''}
                    </td>
                    <td>
                      <StatusBadge tone={status.tone}>
                        {status.label}
                      </StatusBadge>
                      {event.status === 'rejected' &&
                        event.rejection_reason && (
                          <span
                            title={event.rejection_reason}
                            className="mt-1 line-clamp-2 max-w-64 text-[13px] text-danger"
                          >
                            {event.rejection_reason}
                          </span>
                        )}
                    </td>
                    <td>
                      <div className="flex justify-end gap-2">
                        {event.status !== 'pending_approval' &&
                          event.status !== 'rejected' && (
                            <ButtonLink
                              variant="ghost"
                              size="sm"
                              to={`/organizer/events/${event.id}/sales`}
                            >
                              Sales
                            </ButtonLink>
                          )}
                        {/* Matches are curated by admins; organizers can't edit them */}
                        {!terminal && event.event_type !== 'sports_match' && (
                          <ButtonLink
                            variant="outline"
                            size="sm"
                            to={`/organizer/events/${event.id}`}
                          >
                            Edit
                          </ButtonLink>
                        )}
                        {!terminal && <CancelEventButton event={event} />}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
