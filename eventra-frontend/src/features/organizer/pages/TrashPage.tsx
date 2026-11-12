import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { LoadingBlock } from '@/components/LoadingBlock'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { StatusBadge } from '@/components/StatusBadge'
import { TableFrame } from '@/components/TableFrame'
import { Button } from '@/components/ui/button'
import { EventTitleCell } from '@/features/events/components/EventTitleCell'
import { useEventLookups } from '@/features/events/lookups'
import { EVENT_STATUS } from '@/features/events/status'
import type { EventItem } from '@/features/events/types'
import { errorMessage } from '@/lib/api-client'
import { pageParam } from '@/lib/ids'
import { usePageTitle } from '@/lib/use-page-title'
import { useDeleteForever, useRestoreEvent, useTrashedEvents } from '../api'

function RestoreButton({ event }: { event: EventItem }) {
  const restore = useRestoreEvent()
  return (
    <Button
      variant="outline"
      size="sm"
      disabled={restore.isPending}
      onClick={() =>
        restore.mutate(event.id, {
          onSuccess: () =>
            toast.success('Event restored', { description: event.title }),
          onError: (caught) =>
            toast.error(
              errorMessage(caught, 'The event could not be restored.'),
            ),
        })
      }
    >
      Restore
    </Button>
  )
}

function DeleteForeverButton({ event }: { event: EventItem }) {
  const [open, setOpen] = useState(false)
  const remove = useDeleteForever()

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) remove.reset()
      }}
      trigger={
        <Button variant="destructive" size="sm">
          Delete forever
        </Button>
      }
      title="Delete forever?"
      description={
        <>
          <strong className="font-medium text-foreground">{event.title}</strong>{' '}
          will be gone for good. An event that sold tickets can't be deleted:
          its bookings and payments are kept.
        </>
      }
      confirmLabel="Delete forever"
      destructive
      pending={remove.isPending}
      onConfirm={() =>
        remove.mutate(event.id, {
          onSuccess: () => {
            setOpen(false)
            toast.success('Event deleted forever')
          },
        })
      }
    >
      {remove.isError && (
        <Notice tone="error">
          {errorMessage(remove.error, 'The event could not be deleted.')}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

// Shared by both workspaces: the backend returns an organizer's own deleted
// events and every deleted event to an admin
export function TrashPage() {
  usePageTitle('Trash')
  const [params, setParams] = useSearchParams()
  const page = pageParam(params.get('page'))
  const events = useTrashedEvents(page)
  const list = events.data?.results ?? []
  const { resolve } = useEventLookups(list)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Trash"
        description="Deleted events. Restore one to bring it back, or delete it forever if it never sold a ticket."
      />

      {events.isError ? (
        <Notice tone="error">{events.error.message}</Notice>
      ) : events.isPending ? (
        <LoadingBlock label="Loading deleted events" className="h-64" />
      ) : list.length === 0 ? (
        <EmptyState
          title="Trash is empty"
          body="Cancelled and ended events you delete show up here."
        />
      ) : (
        <>
          <TableFrame dimmed={events.isPlaceholderData}>
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
                return (
                  <tr key={event.id}>
                    <EventTitleCell event={event} linked={false} />
                    <td className="text-muted-foreground">
                      {venue ? `${venue.name}, ${venue.city}` : ''}
                    </td>
                    <td>
                      <StatusBadge tone={status.tone}>
                        {status.label}
                      </StatusBadge>
                    </td>
                    <td>
                      <div className="flex justify-end gap-2">
                        <RestoreButton event={event} />
                        <DeleteForeverButton event={event} />
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </TableFrame>
          <Pagination
            page={page}
            count={events.data.count}
            hasPrevious={Boolean(events.data.previous)}
            hasNext={Boolean(events.data.next)}
            onPage={(next) => setParams(next > 1 ? { page: String(next) } : {})}
          />
        </>
      )}
    </div>
  )
}
