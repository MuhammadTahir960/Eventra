import { useQueries, useQuery } from '@tanstack/react-query'
import { apiDownload, apiFetch } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import type { Page } from '@/lib/pagination'
import type { EventItem } from '@/features/events/types'

export type TicketStatus = 'valid' | 'used' | 'cancelled'

// Shape of the backend's TicketSerializer
export interface Ticket {
  id: string
  booking: string
  event_id: string
  event_title: string
  section: string
  row_label: string
  seat_number: number
  // What the QR code encodes; staff scan it at the door
  ticket_code: string
  attendee_name: string
  status: TicketStatus
  created_at: string
}

export const TICKET_STATUS: Record<
  TicketStatus,
  { label: string; tone: 'success' | 'neutral' | 'danger' }
> = {
  valid: { label: 'Valid', tone: 'success' },
  used: { label: 'Used', tone: 'neutral' },
  cancelled: { label: 'Cancelled', tone: 'danger' },
}

// shortcut: only the first page (50 tickets, newest first); add paging if
// one account ever holds more
export function useMyTickets() {
  return useQuery({
    queryKey: ['tickets', 'mine'],
    queryFn: ({ signal }) => apiFetch<Page<Ticket>>('/tickets/', { signal }),
  })
}

export function useTicket(id: string | undefined) {
  return useQuery({
    queryKey: ['tickets', 'detail', id],
    queryFn: ({ signal }) => apiFetch<Ticket>(`/tickets/${id}/`, { signal }),
    enabled: isUuid(id),
    retry: false,
  })
}

// Tickets carry only the event's id and title; dates and venues come from
// the events themselves. A cancelled event may no longer be visible (404),
// so a failed lookup just leaves that event's details out.
export function useEventsById(ids: string[]) {
  const results = useQueries({
    queries: ids.map((id) => ({
      queryKey: ['events', 'detail', id],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiFetch<EventItem>(`/events/${id}/`, { signal }),
      retry: false,
    })),
  })
  const byId = new Map<string, EventItem>()
  for (const result of results) {
    if (result.data) byId.set(result.data.id, result.data)
  }
  return { byId, isPending: results.some((result) => result.isPending) }
}

export async function downloadTicketPdf(ticket: Ticket) {
  const blob = await apiDownload(`/tickets/${ticket.id}/download/`)
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `ticket-${ticket.ticket_code}.pdf`
  link.click()
  // Give the browser a moment to start the download before freeing it
  setTimeout(() => URL.revokeObjectURL(url), 10_000)
}
