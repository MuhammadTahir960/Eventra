import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useTicketTiers } from '@/features/events/hooks'
import { useEventLookups, type EventRefs } from '@/features/events/lookups'
import { CancelEventButton } from '@/features/organizer/pages/OrganizerEventsPage'
import { ApiError } from '@/lib/api-client'
import { formatDateTimeLong, formatMoney } from '@/lib/format'
import {
  useApproveEvent,
  usePendingEvents,
  useRejectEvent,
  type PendingEventItem,
} from '../api'
import { usePageTitle } from '@/lib/use-page-title'
import { toast } from 'sonner'

const errorText = (caught: unknown, fallback: string) =>
  caught instanceof ApiError ? caught.message : fallback

function PendingEvent({
  event,
  refs,
}: {
  event: PendingEventItem
  refs: EventRefs
}) {
  const tiers = useTicketTiers(event.id)
  const approve = useApproveEvent()
  const reject = useRejectEvent()
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [reasonMissing, setReasonMissing] = useState(false)
  const { venue, category, home, away } = refs

  return (
    <article className="rounded-lg border border-border bg-card p-5 sm:p-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <p className="tabular text-[13px] font-medium text-ember-deep">
            {formatDateTimeLong(event.start_datetime)}
          </p>
          <h2 className="mt-1 font-display text-[30px] leading-tight">
            <Link
              to={`/events/${event.id}`}
              className="underline-offset-4 hover:underline"
            >
              {event.title}
            </Link>
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {[
              home && away ? `${home.name} v ${away.name}` : null,
              category?.name,
              venue && `${venue.name}, ${venue.city}`,
            ]
              .filter(Boolean)
              .join('. ')}
          </p>
          {event.has_paid_bookings && (
            <div className="mt-3 flex flex-col items-start gap-1.5">
              <StatusBadge tone="warning">Has paid bookings</StatusBadge>
              <p className="text-sm text-muted-foreground">
                Rejecting would leave buyers without a refund. Approve the
                changes, or cancel the event to refund every buyer.
              </p>
            </div>
          )}
        </div>
        <div className="flex shrink-0 gap-2">
          {event.has_paid_bookings ? (
            <CancelEventButton event={event} size="default" />
          ) : (
            <ConfirmDialog
              open={rejecting}
              onOpenChange={(open) => {
                setRejecting(open)
                if (!open) reject.reset()
              }}
              trigger={<Button variant="destructive">Reject</Button>}
              title="Reject this event?"
              description="The organizer sees your reason and can edit the event and resubmit it."
              confirmLabel="Reject event"
              destructive
              pending={reject.isPending}
              onConfirm={() => {
                // The backend requires a reason; say so here instead of
                // showing its raw error message
                if (!reason.trim()) return setReasonMissing(true)
                reject.mutate(
                  { id: event.id, reason: reason.trim() },
                  {
                    onSuccess: () => {
                      setRejecting(false)
                      toast.success('Event rejected', {
                        description: 'The organizer can see your reason.',
                      })
                    },
                  },
                )
              }}
            >
              <FormField
                id={`reason-${event.id}`}
                label="Reason for the organizer"
                error={
                  reasonMissing
                    ? 'Tell the organizer what to change.'
                    : undefined
                }
              >
                {(control) => (
                  <Textarea
                    {...control}
                    rows={3}
                    maxLength={2000}
                    value={reason}
                    onChange={(e) => {
                      setReason(e.target.value)
                      setReasonMissing(false)
                    }}
                  />
                )}
              </FormField>
              {reject.isError && (
                <Notice tone="error" className="mt-3">
                  {errorText(reject.error, 'The event could not be rejected.')}
                </Notice>
              )}
            </ConfirmDialog>
          )}
          <Button
            variant="ink"
            disabled={approve.isPending}
            onClick={() =>
              approve.mutate(event.id, {
                onSuccess: () =>
                  toast.success('Event approved', {
                    description: `${event.title} is now on sale.`,
                  }),
              })
            }
          >
            {approve.isPending ? 'Approving…' : 'Approve'}
          </Button>
        </div>
      </div>

      {approve.isError && (
        <Notice tone="error" className="mt-4">
          {errorText(approve.error, 'The event could not be approved.')}
        </Notice>
      )}

      <p className="mt-4 line-clamp-3 max-w-[70ch] text-[15px] whitespace-pre-line">
        {event.description}
      </p>

      {tiers.data && tiers.data.length > 0 && (
        <ul className="mt-4 flex flex-wrap gap-2">
          {tiers.data.map((tier) => (
            <li
              key={tier.id}
              className="rounded-full border border-border px-3 py-1 text-[13px]"
            >
              {tier.name}{' '}
              <span className="tabular font-medium">
                {formatMoney(tier.price)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </article>
  )
}

export function ModerationPage() {
  usePageTitle('Moderation')
  const pending = usePendingEvents()
  const list = pending.data?.results ?? []
  const { resolve } = useEventLookups(list)

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Moderation"
        description={
          pending.data
            ? `${pending.data.count.toLocaleString()} ${pending.data.count === 1 ? 'event' : 'events'} waiting for review, oldest first.`
            : undefined
        }
      />
      {pending.isError ? (
        <Notice tone="error">{pending.error.message}</Notice>
      ) : pending.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading queue"
          className="h-64 animate-pulse rounded-lg bg-muted"
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="All caught up"
          body="New events from organizers appear here for review."
        />
      ) : (
        <div className="flex flex-col gap-4">
          {list.map((event) => (
            <PendingEvent key={event.id} event={event} refs={resolve(event)} />
          ))}
        </div>
      )}
    </div>
  )
}
