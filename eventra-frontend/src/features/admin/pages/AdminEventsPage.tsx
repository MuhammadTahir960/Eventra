import { type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { useEventLookups } from '@/features/events/lookups'
import { EVENT_STATUS } from '@/features/events/status'
import type { EventItem, EventStatus } from '@/features/events/types'
import {
  CancelEventButton,
  RunningLateButton,
} from '@/features/organizer/pages/OrganizerEventsPage'
import { canRunLate } from '@/features/organizer/running-late'
import { ApiError } from '@/lib/api-client'
import { formatDateTime } from '@/lib/format'
import { pageParam } from '@/lib/ids'
import { cn } from '@/lib/utils'
import { useAdminEvents, useRetryRefunds, type AdminEventFilters } from '../api'
import { usePageTitle } from '@/lib/use-page-title'
import { toast } from 'sonner'

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
          {retry.error instanceof ApiError
            ? retry.error.message
            : 'Could not queue refunds.'}
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

  function onSearch(submit: FormEvent<HTMLFormElement>) {
    submit.preventDefault()
    const value = new FormData(submit.currentTarget).get('q')
    setFilters({
      ...filters,
      search: typeof value === 'string' ? value : '',
      page: 1,
    })
  }

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Events"
        description="Every event on the platform, including removed ones."
        actions={
          <ButtonLink variant="ink" to="/organizer/events/new">
            Create event or match
          </ButtonLink>
        }
      />

      <div className="flex flex-col gap-3 sm:flex-row">
        {/* key remounts the box when the URL search changes (back button) */}
        <form
          key={filters.search}
          role="search"
          onSubmit={onSearch}
          className="flex flex-1 gap-2"
        >
          <label htmlFor="admin-event-search" className="sr-only">
            Search events
          </label>
          <Input
            id="admin-event-search"
            name="q"
            type="search"
            maxLength={100}
            placeholder="Search title or description…"
            defaultValue={filters.search}
          />
          <Button type="submit" variant="outline">
            Search
          </Button>
        </form>
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
        <div
          aria-busy="true"
          aria-label="Loading events"
          className="h-64 animate-pulse rounded-lg bg-muted"
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No events match"
          body="Try another status or search."
        />
      ) : (
        <>
          <div
            className={cn(
              'relative overflow-x-auto rounded-lg border border-border bg-card',
              events.isPlaceholderData && 'opacity-60',
            )}
          >
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
                        <span className="flex flex-wrap gap-1.5">
                          <StatusBadge tone={status.tone}>
                            {status.label}
                          </StatusBadge>
                          {!event.is_active && (
                            <StatusBadge tone="neutral">Removed</StatusBadge>
                          )}
                        </span>
                      </td>
                      <td>
                        <div className="flex justify-end gap-2">
                          {event.status === 'cancelled' && (
                            <RetryRefundsButton event={event} />
                          )}
                          {canRunLate(event) && (
                            <RunningLateButton event={event} />
                          )}
                          {/* Completed events are voided from the payouts page */}
                          {event.status !== 'cancelled' &&
                            event.status !== 'completed' && (
                              <CancelEventButton event={event} />
                            )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
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
