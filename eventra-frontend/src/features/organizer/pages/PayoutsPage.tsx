import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ApiError, apiFetch } from '@/lib/api-client'
import { formatDateTime, formatMoney } from '@/lib/format'
import {
  PAYOUT_STATUS,
  useAwaitingPayouts,
  usePayOut,
  usePayouts,
  type AwaitingPayout,
  type Payout,
} from '../api'
import { usePageTitle } from '@/lib/use-page-title'
import { CancelEventButton } from './OrganizerEventsPage'
import { toast } from 'sonner'

function RetryButton({ payout }: { payout: Payout }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const settle = useMutation({
    mutationFn: () =>
      apiFetch<Payout>(`/admin/payouts/${payout.id}/settle/`, {
        method: 'POST',
      }),
    onSuccess: () => {
      setOpen(false)
      toast.success('Payout is being retried', {
        description: 'Its status updates once it completes.',
      })
      void client.invalidateQueries({ queryKey: ['admin', 'payouts'] })
    },
  })

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) settle.reset()
      }}
      trigger={
        <Button variant="outline" size="sm">
          Retry
        </Button>
      }
      title="Retry this payout?"
      description={`Tries again to pay ${formatMoney(payout.net_amount)} for "${payout.event_title}" to the organizer.`}
      confirmLabel="Retry payout"
      pending={settle.isPending}
      onConfirm={() => settle.mutate()}
    >
      {settle.isError && (
        <Notice tone="error">
          {settle.error instanceof ApiError
            ? settle.error.message
            : 'The payout could not be retried.'}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

function PayOutButton({ row }: { row: AwaitingPayout }) {
  const [open, setOpen] = useState(false)
  const payOut = usePayOut()

  return (
    <ConfirmDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) payOut.reset()
      }}
      trigger={
        <Button variant="ink" size="sm">
          Pay out
        </Button>
      }
      title="Pay out this event?"
      description={`Pays ${formatMoney(row.net_amount)} for "${row.event_title}" to ${row.organizer_name}. After this the event can no longer be voided.`}
      confirmLabel="Pay out"
      pending={payOut.isPending}
      onConfirm={() =>
        payOut.mutate(row.event_id, {
          onSuccess: () => {
            setOpen(false)
            toast.success('Payout is on its way', {
              description: 'Its status updates once it settles.',
            })
          },
        })
      }
    >
      {payOut.isError && (
        <Notice tone="error">
          {payOut.error instanceof ApiError
            ? payOut.error.message
            : 'The payout could not be made.'}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

// Completed events waiting for their payout. Admins pay them out once the
// 24 hours after completion are up; organizers see when that will be.
function AwaitingPayouts({ scope }: { scope: 'organizer' | 'admin' }) {
  const awaiting = useAwaitingPayouts(scope)
  const rows = awaiting.data?.results ?? []

  if (awaiting.isError)
    return <Notice tone="error">{awaiting.error.message}</Notice>
  if (awaiting.isPending || rows.length === 0) return null

  return (
    <section className="flex flex-col gap-3">
      <h2 className="font-display text-2xl">
        {scope === 'admin' ? 'Ready to pay out' : 'Upcoming'}
      </h2>
      <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
        <table className="data-table">
          <thead>
            <tr>
              <th scope="col">Event</th>
              <th scope="col" className="num">
                Net
              </th>
              <th scope="col" className="text-right">
                Payout
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.event_id}>
                <td className="min-w-56">
                  <span className="font-medium">{row.event_title}</span>
                  <span className="tabular block text-[13px] text-muted-foreground">
                    {scope === 'admin' && `${row.organizer_name} · `}
                    Ended {formatDateTime(row.completed_at)}
                  </span>
                </td>
                <td className="num font-semibold">
                  {formatMoney(row.net_amount)}
                </td>
                <td>
                  <div className="flex items-center justify-end gap-2">
                    {scope === 'admin' && row.eligible ? (
                      <PayOutButton row={row} />
                    ) : (
                      <span className="tabular text-[13px] text-muted-foreground">
                        {scope === 'admin' || !row.eligible
                          ? `Available from ${formatDateTime(row.payout_available_at)}`
                          : 'Waiting for an admin'}
                      </span>
                    )}
                    {/* Pay the organizer or refund the buyers: one decision, one place */}
                    {scope === 'admin' && (
                      <CancelEventButton
                        event={{
                          id: row.event_id,
                          title: row.event_title,
                          status: 'completed',
                        }}
                      />
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

// One page for both roles: organizers see their own payouts, admins see
// everyone's, pay out events that are ready and retry failed payouts
export function PayoutsPage({ scope }: { scope: 'organizer' | 'admin' }) {
  usePageTitle('Payouts')
  const payouts = usePayouts(scope)
  const list = payouts.data?.results ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Payouts"
        description={
          scope === 'organizer'
            ? 'Paid by an admin from 24 hours after each event ends: ticket sales minus the 10% platform fee.'
            : 'Events become ready to pay out 24 hours after they end. Until they are paid out, they can be voided instead.'
        }
      />

      <AwaitingPayouts scope={scope} />

      {payouts.isError ? (
        <Notice tone="error">{payouts.error.message}</Notice>
      ) : payouts.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading payouts"
          className="h-64 animate-pulse rounded-lg bg-muted"
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No payouts yet"
          body="A payout appears here once an event with ticket sales has finished."
        />
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Event</th>
                <th scope="col" className="num">
                  Gross
                </th>
                <th scope="col" className="num">
                  Fee
                </th>
                <th scope="col" className="num">
                  Net
                </th>
                <th scope="col">Status</th>
                {scope === 'admin' && (
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {list.map((payout) => {
                const status = PAYOUT_STATUS[payout.status]
                return (
                  <tr key={payout.id}>
                    <td className="min-w-56">
                      <span className="font-medium">{payout.event_title}</span>
                      <span className="tabular block text-[13px] text-muted-foreground">
                        {payout.settled_at
                          ? `Settled ${formatDateTime(payout.settled_at)}`
                          : `Created ${formatDateTime(payout.created_at)}`}
                      </span>
                    </td>
                    <td className="num">{formatMoney(payout.gross_revenue)}</td>
                    <td className="num text-muted-foreground">
                      {formatMoney(payout.platform_fee)}
                    </td>
                    <td className="num font-semibold">
                      {formatMoney(payout.net_amount)}
                    </td>
                    <td>
                      <StatusBadge tone={status.tone}>
                        {status.label}
                      </StatusBadge>
                    </td>
                    {scope === 'admin' && (
                      <td className="text-right">
                        {/* Payouts start settling when created; only a failed one needs a hand */}
                        {(payout.status === 'pending' ||
                          payout.status === 'failed') && (
                          <RetryButton payout={payout} />
                        )}
                      </td>
                    )}
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
