import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowLeft01Icon, Download04Icon } from '@hugeicons/core-free-icons'
import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Logo } from '@/components/Logo'
import { Notice } from '@/components/Notice'
import { StatusBadge } from '@/components/StatusBadge'
import { TicketStub } from '@/components/TicketStub'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { useEventLookups } from '@/features/events/lookups'
import { ApiError } from '@/lib/api-client'
import { formatDateTimeLong } from '@/lib/format'
import { isUuid } from '@/lib/ids'
import { cn } from '@/lib/utils'
import {
  TICKET_STATUS,
  downloadTicketPdf,
  useEventsById,
  useTicket,
} from '../api'
import { CopyCode } from '../components/CopyCode'
import { TicketQr } from '../components/TicketQr'
import { usePageTitle } from '@/lib/use-page-title'

export function TicketPage() {
  const { id } = useParams()
  const ticket = useTicket(id)
  usePageTitle(ticket.data ? `Ticket: ${ticket.data.event_title}` : 'Ticket')
  const events = useEventsById(ticket.data ? [ticket.data.event_id] : [])
  const event = ticket.data ? events.byId.get(ticket.data.event_id) : undefined
  const { resolve } = useEventLookups(event ? [event] : undefined)
  const [downloading, setDownloading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (
    !isUuid(id) ||
    (ticket.error instanceof ApiError && ticket.error.status === 404)
  ) {
    return (
      <div className="gutter mx-auto max-w-[640px] pt-16">
        <EmptyState
          title="Ticket not found"
          body="It may belong to another account, or the link is wrong."
          action={
            <ButtonLink variant="ink" to="/bookings">
              My tickets
            </ButtonLink>
          }
        />
      </div>
    )
  }

  if (ticket.isPending) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading ticket"
        className="gutter mx-auto max-w-[480px] pt-10"
      >
        <div className="h-[560px] animate-pulse rounded-lg bg-muted" />
      </div>
    )
  }

  if (ticket.isError) {
    return (
      <div className="gutter mx-auto max-w-xl pt-16">
        <Notice tone="error">{ticket.error.message}</Notice>
      </div>
    )
  }

  const item = ticket.data
  const status = TICKET_STATUS[item.status]
  const venue = event ? resolve(event).venue : undefined

  async function download() {
    setDownloading(true)
    setError(null)
    try {
      await downloadTicketPdf(item)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'The PDF could not be downloaded.',
      )
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="gutter mx-auto flex max-w-[480px] flex-col gap-6 pt-6">
      <Link
        to="/bookings"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
      >
        <HugeiconsIcon icon={ArrowLeft01Icon} size={16} aria-hidden />
        My tickets
      </Link>

      <TicketStub
        as="article"
        aria-label={`Ticket for ${item.event_title}`}
        stub={
          <div className="flex flex-col items-center gap-3 py-2">
            <TicketQr code={item.ticket_code} />
            <CopyCode code={item.ticket_code} />
            <p className="text-center text-[13px] text-muted-foreground">
              Show this code at the entrance.
            </p>
          </div>
        }
      >
        <div className="flex items-center justify-between">
          <Logo size={22} />
          <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
        </div>
        <h1
          className={cn(
            'mt-6 font-display leading-[1.05] wrap-anywhere',
            // A ticket shows the full name, so long titles step down a size
            item.event_title.length > 60
              ? 'text-[clamp(1.75rem,6vw,2.125rem)]'
              : 'text-[clamp(2.25rem,8vw,2.75rem)]',
          )}
        >
          {item.event_title}
        </h1>
        {event && (
          <time
            dateTime={event.start_datetime}
            className="tabular mt-2 block text-[15px] font-medium text-ember-deep"
          >
            {formatDateTimeLong(event.start_datetime)}
          </time>
        )}
        {venue && (
          <p className="mt-1 text-sm text-muted-foreground">
            {venue.name}, {venue.address}, {venue.city}
          </p>
        )}

        {/* Section names run to 50 characters, so it spans the full width */}
        <dl className="mt-6 grid grid-cols-2 gap-4 border-t border-border pt-5">
          {[
            ['Section', item.section],
            ['Row', item.row_label],
            ['Seat', String(item.seat_number)],
          ].map(([label, value], index) => (
            <div key={label} className={index === 0 ? 'col-span-2' : undefined}>
              <dt className="text-[13px] text-muted-foreground">{label}</dt>
              <dd className="tabular mt-0.5 text-xl font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      </TicketStub>

      {error && <Notice tone="error">{error}</Notice>}
      <Button
        variant="ink"
        size="lg"
        onClick={() => void download()}
        disabled={downloading}
      >
        <HugeiconsIcon icon={Download04Icon} size={18} />
        {downloading ? 'Preparing PDF…' : 'Download PDF'}
      </Button>
    </div>
  )
}
