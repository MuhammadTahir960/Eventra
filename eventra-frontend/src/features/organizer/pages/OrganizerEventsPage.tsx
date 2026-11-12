import { useState } from 'react'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { HoldToConfirmButton } from '@/components/HoldToConfirmButton'
import { EmptyState } from '@/components/EmptyState'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { Input } from '@/components/ui/input'
import { useEventLookups } from '@/features/events/lookups'
import { EVENT_STATUS, TERMINAL } from '@/features/events/status'
import type { EventItem } from '@/features/events/types'
import { errorMessage, firstFieldErrors } from '@/lib/api-client'
import { toLocalInput } from '@/lib/format'
import {
  useCancelEvent,
  useMoveToTrash,
  useOrganizerEvents,
  usePostponeEvent,
  useRestoreEvent,
  useRunningLate,
} from '../api'
import { canPostpone, canRunLate } from '../running-late'
import { usePageTitle } from '@/lib/use-page-title'
import { EventTitleCell } from '@/features/events/components/EventTitleCell'
import { TableFrame } from '@/components/TableFrame'
import { LoadingBlock } from '@/components/LoadingBlock'

export function RunningLateButton({ event }: { event: EventItem }) {
  const [open, setOpen] = useState(false)
  const [end, setEnd] = useState('')
  const [missing, setMissing] = useState(false)
  const runLate = useRunningLate(event.id)
  const fieldError = missing
    ? 'Pick a new end time.'
    : firstFieldErrors(runLate.error).end_datetime

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) setEnd(toLocalInput(event.end_datetime))
        else runLate.reset()
        setMissing(false)
      }}
      trigger={
        <Button variant="outline" size="sm">
          Running late
        </Button>
      }
      title="Running late?"
      description={
        <>
          Move the end of{' '}
          <strong className="font-medium text-foreground">{event.title}</strong>{' '}
          later, for a delayed start, an overrun or a match finished the next
          day. Tickets stay valid; buyers are emailed if it moves to another
          day.
        </>
      }
      confirmLabel="Save new end time"
      pending={runLate.isPending}
      onConfirm={() => {
        if (!end) return setMissing(true)
        runLate.mutate(new Date(end).toISOString(), {
          onSuccess: () => {
            setOpen(false)
            toast.success('End time updated')
          },
        })
      }}
    >
      <FormField
        id={`late-end-${event.id}`}
        label="Now ends"
        error={fieldError}
      >
        {(control) => (
          <Input
            {...control}
            type="datetime-local"
            value={end}
            min={toLocalInput(event.end_datetime)}
            onChange={(e) => {
              setEnd(e.target.value)
              setMissing(false)
            }}
          />
        )}
      </FormField>
      {runLate.isError && !fieldError && (
        <Notice tone="error" className="mt-3">
          {errorMessage(runLate.error, 'The end time could not be changed.')}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

export function PostponeButton({ event }: { event: EventItem }) {
  const [open, setOpen] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [missing, setMissing] = useState(false)
  const postpone = usePostponeEvent(event.id)
  const fields = firstFieldErrors(postpone.error)
  const startError =
    missing && !start ? 'Pick the new start.' : fields.start_datetime
  const endError = missing && !end ? 'Pick the new end.' : fields.end_datetime

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (next) {
          setStart(toLocalInput(event.start_datetime))
          setEnd(toLocalInput(event.end_datetime))
        } else postpone.reset()
        setMissing(false)
      }}
      trigger={
        <Button variant="outline" size="sm">
          Postpone
        </Button>
      }
      title="Postpone this event?"
      description={
        <>
          Move{' '}
          <strong className="font-medium text-foreground">{event.title}</strong>{' '}
          to a later date. Tickets stay valid. Buyers are emailed and can get a
          full refund until a day before the new date.
        </>
      }
      confirmLabel="Postpone event"
      pending={postpone.isPending}
      onConfirm={() => {
        if (!start || !end) return setMissing(true)
        postpone.mutate(
          {
            start_datetime: new Date(start).toISOString(),
            end_datetime: new Date(end).toISOString(),
          },
          {
            onSuccess: () => {
              setOpen(false)
              toast.success('Event postponed', {
                description: 'Buyers are being emailed the new date.',
              })
            },
          },
        )
      }}
    >
      <div className="flex flex-col gap-4">
        <FormField
          id={`postpone-start-${event.id}`}
          label="New start"
          error={startError}
        >
          {(control) => (
            <Input
              {...control}
              type="datetime-local"
              value={start}
              min={toLocalInput(event.start_datetime)}
              onChange={(e) => {
                setStart(e.target.value)
                setMissing(false)
              }}
            />
          )}
        </FormField>
        <FormField
          id={`postpone-end-${event.id}`}
          label="New end"
          error={endError}
        >
          {(control) => (
            <Input
              {...control}
              type="datetime-local"
              value={end}
              min={start}
              onChange={(e) => {
                setEnd(e.target.value)
                setMissing(false)
              }}
            />
          )}
        </FormField>
      </div>
      {postpone.isError && !startError && !endError && (
        <Notice tone="error" className="mt-3">
          {errorMessage(postpone.error, 'The event could not be postponed.')}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

// Cancelling refunds every buyer, so it always goes through a confirmation
export function CancelEventButton({
  event,
  size = 'sm',
}: {
  // Only these fields, so the payouts page can void from a payout row
  event: Pick<EventItem, 'id' | 'title' | 'status'>
  size?: 'sm' | 'default'
}) {
  const [open, setOpen] = useState(false)
  const cancel = useCancelEvent()
  const [error, setError] = useState<string | null>(null)
  // Bumped after a failure so the hold button re-arms
  const [attempt, setAttempt] = useState(0)
  const hintId = `cancel-hint-${event.id}`
  // An ended event is voided (abandoned or didn't happen), not cancelled
  const voiding = event.status === 'completed'

  function confirm() {
    cancel.mutate(event.id, {
      onSuccess: () => {
        setOpen(false)
        toast.success(voiding ? 'Event voided' : 'Event cancelled', {
          description: 'Every buyer is being refunded in full.',
        })
      },
      onError: (caught) => {
        setError(errorMessage(caught, 'The event could not be cancelled.'))
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
          {voiding ? 'Void' : 'Cancel'}
        </Button>
      }
      title={voiding ? 'Void and refund everyone?' : 'Cancel this event?'}
      description={
        voiding ? (
          <>
            <strong className="font-medium text-foreground">
              {event.title}
            </strong>{' '}
            has ended. Use this only if it didn't take place or was abandoned.
            Every buyer gets a full refund and no payout is made. This can't be
            undone.
          </>
        ) : (
          <>
            <strong className="font-medium text-foreground">
              {event.title}
            </strong>{' '}
            will be taken off sale and every buyer is refunded in full. This
            can't be undone.
          </>
        )
      }
      confirmLabel={voiding ? 'Void event' : 'Cancel event'}
      destructive
      pending={cancel.isPending}
      onConfirm={confirm}
      // Refunding every buyer is the most destructive action in the app, so
      // it takes a deliberate hold rather than one click
      confirmControl={
        <HoldToConfirmButton
          key={attempt}
          label={voiding ? 'Hold to void event' : 'Hold to cancel event'}
          confirmedLabel={voiding ? 'Voiding…' : 'Cancelling…'}
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

// Reversible from the trash, so no confirmation: the toast offers Undo instead
export function MoveToTrashButton({ event }: { event: EventItem }) {
  const trash = useMoveToTrash()
  const restore = useRestoreEvent()
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={trash.isPending}
      onClick={() =>
        trash.mutate(event.id, {
          onSuccess: () =>
            toast.success('Moved to trash', {
              description: event.title,
              action: {
                label: 'Undo',
                // The row is gone by now, so report a failure here
                onClick: () =>
                  void restore
                    .mutateAsync(event.id)
                    .catch((caught: unknown) =>
                      toast.error(
                        errorMessage(
                          caught,
                          'The event could not be restored.',
                        ),
                      ),
                    ),
              },
            }),
          onError: (caught) =>
            toast.error(
              errorMessage(
                caught,
                'The event could not be moved to the trash.',
              ),
            ),
        })
      }
    >
      Move to trash
    </Button>
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
        <LoadingBlock label="Loading events" className="h-64" />
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
        <TableFrame>
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
                  <EventTitleCell event={event} />
                  <td className="text-muted-foreground">
                    {venue ? `${venue.name}, ${venue.city}` : ''}
                  </td>
                  <td>
                    <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
                    {event.status === 'rejected' && event.rejection_reason && (
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
                      {event.status === 'approved' && (
                        <ButtonLink
                          variant="ghost"
                          size="sm"
                          to={`/organizer/events/${event.id}/door`}
                        >
                          Door
                        </ButtonLink>
                      )}
                      {canPostpone(event) && <PostponeButton event={event} />}
                      {canRunLate(event) && <RunningLateButton event={event} />}
                      {!terminal && <CancelEventButton event={event} />}
                      {terminal && <MoveToTrashButton event={event} />}
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </TableFrame>
      )}
    </div>
  )
}
