import { Link, useParams } from 'react-router-dom'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { useEvent } from '@/features/events/hooks'
import { ApiError } from '@/lib/api-client'
import { formatMoney } from '@/lib/format'
import { toCents } from '@/lib/money'
import { useEventSales } from '../api'
import { usePageTitle } from '@/lib/use-page-title'

// Same maths as the backend (PLATFORM_FEE_PERCENTAGE in payouts/services.py):
// a 10% fee rounded half-up to the cent, worked out in whole cents
function netAfterFee(gross: string): string {
  const cents = toCents(gross)
  const fee = Math.round(cents / 10)
  return ((cents - fee) / 100).toFixed(2)
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-border bg-card p-5">
      <p className="text-[13px] text-muted-foreground">{label}</p>
      <p className="tabular mt-1 text-[28px] font-semibold tracking-tight">
        {value}
      </p>
    </div>
  )
}

export function EventSalesPage() {
  const { id } = useParams()
  const event = useEvent(id)
  usePageTitle(event.data ? `Sales: ${event.data.title}` : 'Sales')
  const sales = useEventSales(id)

  if (sales.isError) {
    return (
      <Notice tone="error">
        {sales.error instanceof ApiError
          ? sales.error.message
          : 'Sales could not be loaded.'}
      </Notice>
    )
  }

  const data = sales.data
  const refunded =
    data?.tickets.filter((ticket) => ticket.status === 'refunded').length ?? 0

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Sales"
        description={
          event.data ? (
            <Link
              to={`/events/${event.data.id}`}
              className="underline-offset-4 hover:underline"
            >
              {event.data.title}
            </Link>
          ) : undefined
        }
      />

      {sales.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading sales"
          className="h-64 animate-pulse rounded-lg bg-muted"
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            <Stat
              label="Tickets sold"
              value={String(data!.tickets_sold - refunded)}
            />
            <Stat
              label="Gross sales"
              value={formatMoney(data!.gross_revenue)}
            />
            <Stat
              label="Your share after the 10% fee"
              value={formatMoney(netAfterFee(data!.gross_revenue))}
            />
          </div>
          <p className="-mt-4 text-[13px] text-muted-foreground">
            Your share is an estimate. The exact amount is set when the payout
            is created after the event.
          </p>

          {data!.tickets.length === 0 ? (
            <Notice>No tickets sold yet.</Notice>
          ) : (
            <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
              <table className="data-table">
                <thead>
                  <tr>
                    <th scope="col">Ticket</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="num">
                      Amount
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {data!.tickets.map((ticket) => (
                    <tr key={ticket.ticket_id}>
                      <td className="tabular">{ticket.ticket_code}</td>
                      <td>
                        <StatusBadge
                          tone={
                            ticket.status === 'confirmed' ? 'success' : 'info'
                          }
                        >
                          {ticket.status === 'confirmed' ? 'Sold' : 'Refunded'}
                        </StatusBadge>
                      </td>
                      <td className="num">{formatMoney(ticket.amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  )
}
