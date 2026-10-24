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
import { PAYOUT_STATUS, usePayouts, type Payout } from '../api'
import { usePageTitle } from '@/lib/use-page-title'
import { toast } from 'sonner'

function SettleButton({ payout }: { payout: Payout }) {
  const client = useQueryClient()
  const [open, setOpen] = useState(false)
  const settle = useMutation({
    mutationFn: () =>
      apiFetch<Payout>(`/admin/payouts/${payout.id}/settle/`, {
        method: 'POST',
      }),
    onSuccess: () => {
      setOpen(false)
      toast.success('Payout is settling', {
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
          Settle
        </Button>
      }
      title="Settle this payout?"
      description={`Marks ${formatMoney(payout.net_amount)} for "${payout.event_title}" as paid to the organizer.`}
      confirmLabel="Settle payout"
      pending={settle.isPending}
      onConfirm={() => settle.mutate()}
    >
      {settle.isError && (
        <Notice tone="error">
          {settle.error instanceof ApiError
            ? settle.error.message
            : 'The payout could not be settled.'}
        </Notice>
      )}
    </ConfirmDialog>
  )
}

// One page for both roles: organizers see their own payouts, admins see
// everyone's and can settle the ones that are ready
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
            ? 'Created automatically after each event ends: ticket sales minus the 10% platform fee.'
            : 'Payouts across all organizers. Settle the ones that are ready.'
        }
      />

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
                        {/* The backend settles pending payouts and retries failed ones */}
                        {(payout.status === 'pending' ||
                          payout.status === 'failed') && (
                          <SettleButton payout={payout} />
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
