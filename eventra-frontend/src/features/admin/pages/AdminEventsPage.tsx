import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { useEventLookups } from '@/features/events/lookups'
import { EVENT_STATUS, TERMINAL } from '@/features/events/status'
import type { EventItem, EventStatus } from '@/features/events/types'
import {
  CancelEventButton,
  MoveToTrashButton,
  PostponeButton,
  RunningLateButton,
} from '@/features/organizer/pages/OrganizerEventsPage'
import { canPostpone, canRunLate } from '@/features/organizer/running-late'
import { errorMessage } from '@/lib/api-client'
import { pageParam } from '@/lib/ids'
import { useAdminEvents, useRetryRefunds, type AdminEventFilters } from '../api'
import { toast } from 'sonner'
import { EventTitleCell } from '@/features/events/components/EventTitleCell'
import { TableFrame } from '@/components/TableFrame'
import { LoadingBlock } from '@/components/LoadingBlock'
import { SearchForm } from '@/components/SearchForm'
import { NativeSelect } from '@/components/ui/native-select'
import { usePageTitle } from '@/lib/use-page-title'

function RetryRefundsButton({ event }: { event: EventItem }) {
  const retry = useRetryRefunds()
  return (
    <span className="flex flex-col items-end gap-1">
      <Button
        variant="outline"
        size="sm"
        disabled={retry.isPending || retry.isSuccess}
        onClick={() =>
          retry.mutate(event.id, {
            onSuccess: () => toast.success('Refunds queued for another try'),
          })
        }
      >
        {retry.isSuccess ? 'Refunds queued' : 'Retry refunds'}
      </Button>
      {retry.isError && (
        <span className="text-[13px] text-danger">
          {errorMessage(retry.error, 'Could not queue refunds.')}
        </span>
      )}
    </span>
  )
}

export function AdminEventsPage() {
  usePageTitle('All events')
  // Filters live in the URL so a reload, the back button or a shared link
  // keeps them. The URL is user-editable, so values go through an allow-list.
  const [params, setParams] = useSearchParams()
  const status = params.get('status') ?? ''
  const filters: AdminEventFilters = {
    status: Object.hasOwn(EVENT_STATUS, status) ? (status as EventStatus) : '',
    search: (params.get('q') ?? '').slice(0, 100),
    page: pageParam(params.get('page')),
  }
  function setFilters(next: AdminEventFilters) {
    const query: Record<string, string> = {}
    if (next.status) query.status = next.status
    if (next.search) query.q = next.search
    if (next.page > 1) query.page = String(next.page)
    setParams(query)
  }
  const events = useAdminEvents(filters)
  const list = events.data?.results ?? []
  const { resolve } = useEventLookups(list)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Events"
        description="Every event on the platform. Deleted events are in the trash."
        actions={
          <ButtonLink variant="ink" to="/organizer/events/new">
            Create event or match
          </ButtonLink>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row">
        <SearchForm
          id="admin-event-search"
          label="Search events"
          placeholder="Search title or description…"
          value={filters.search}
          onSearch={(search) => setFilters({ ...filters, search, page: 1 })}
        />
        <label htmlFor="admin-event-status" className="sr-only">
          Status
        </label>
        <NativeSelect
          id="admin-event-status"
          className="sm:w-52"
          value={filters.status}
          onChange={(e) =>
            setFilters({
              ...filters,
              status: e.target.value as EventStatus | '',
              page: 1,
            })
          }
        >
          <option value="">All statuses</option>
          {(Object.keys(EVENT_STATUS) as EventStatus[]).map((status) => (
            <option key={status} value={status}>
              {EVENT_STATUS[status].label}
            </option>
          ))}
        </NativeSelect>
      </div>

      {events.isError ? (
        <Notice tone="error">{events.error.message}</Notice>
      ) : events.isPending ? (
        <LoadingBlock label="Loading events" className="h-64" />
      ) : list.length === 0 ? (
        <EmptyState
          title="No events match"
          body="Try another status or search."
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
                    <EventTitleCell event={event} />
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
                        {event.status === 'cancelled' && (
                          <RetryRefundsButton event={event} />
                        )}
                        {event.status === 'approved' && (
                          <ButtonLink
                            variant="ghost"
                            size="sm"
                            to={`/admin/events/${event.id}/door`}
                          >
                            Door
                          </ButtonLink>
                        )}
                        {canPostpone(event) && <PostponeButton event={event} />}
                        {canRunLate(event) && (
                          <RunningLateButton event={event} />
                        )}
                        {/* Completed events are voided from the payouts page */}
                        {event.status !== 'cancelled' &&
                          event.status !== 'completed' && (
                            <CancelEventButton event={event} />
                          )}
                        {TERMINAL.includes(event.status) && (
                          <MoveToTrashButton event={event} />
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </TableFrame>
          <Pagination
            page={filters.page}
            count={events.data.count}
            hasPrevious={Boolean(events.data.previous)}
            hasNext={Boolean(events.data.next)}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </div>
  )
}
