import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import type { Page } from '@/lib/pagination'
import type { StatusTone } from '@/components/StatusBadge'
import type { EventItem } from '@/features/events/types'
import type { Ticket } from '@/features/tickets/api'

// ---------- events ----------

// shortcut: first page only (50 events, newest first); add paging when an
// organizer can realistically have more
export function useOrganizerEvents() {
  return useQuery({
    queryKey: ['organizer', 'events'],
    queryFn: ({ signal }) =>
      apiFetch<Page<EventItem>>('/organizer/events/', { signal }),
  })
}

export type EventPatch = Partial<
  Pick<
    EventItem,
    | 'title'
    | 'description'
    | 'category'
    | 'start_datetime'
    | 'end_datetime'
    | 'max_tickets_per_buyer'
  >
>

export function useUpdateEvent(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (patch: EventPatch) =>
      apiFetch<EventItem>(`/events/${id}/`, { method: 'PATCH', body: patch }),
    onSuccess: (event) => {
      client.setQueryData(['events', 'detail', id], event)
      void client.invalidateQueries({ queryKey: ['organizer', 'events'] })
      void client.invalidateQueries({ queryKey: ['events', 'list'] })
    },
  })
}

// Every list that shows events, after an owner or an admin changes one
function refreshEventLists(client: QueryClient) {
  void client.invalidateQueries({ queryKey: ['organizer'] })
  void client.invalidateQueries({ queryKey: ['admin'] })
  void client.invalidateQueries({ queryKey: ['events', 'list'] })
}

function refreshEvent(client: QueryClient, event: EventItem) {
  client.setQueryData(['events', 'detail', event.id], event)
  refreshEventLists(client)
}

// Owner or admin. Cancelling refunds every booking, so callers confirm first.
export function useCancelEvent() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<EventItem>(`/events/${id}/cancel/`, { method: 'POST' }),
    onSuccess: (event) => refreshEvent(client, event),
  })
}

// Owner or admin: push the end time later (rain delay, overrun, resumed next
// day). No review; ticket holders are emailed if the day changes.
export function useRunningLate(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (endDatetime: string) =>
      apiFetch<EventItem>(`/events/${id}/extend-end/`, {
        method: 'POST',
        body: { end_datetime: endDatetime },
      }),
    onSuccess: (event) => refreshEvent(client, event),
  })
}

// Owner or admin: move the whole event to a later date. Tickets stay valid;
// buyers are emailed and can ask for a refund until a day before.
export function usePostponeEvent(id: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (dates: { start_datetime: string; end_datetime: string }) =>
      apiFetch<EventItem>(`/events/${id}/postponements/`, {
        method: 'POST',
        body: dates,
      }),
    onSuccess: (event) => refreshEvent(client, event),
  })
}

// ---------- door ----------

// Owner or admin. The server decides; refusals come back as 404 or 409.
export function useCheckIn(eventId: string) {
  return useMutation({
    mutationFn: (code: string) =>
      apiFetch<Ticket>(`/events/${eventId}/check-ins/`, {
        method: 'POST',
        body: { code },
      }),
  })
}

// ---------- trash ----------

// The backend scopes it: an organizer's own deleted events, everyone's for an admin
export function useTrashedEvents(page: number) {
  return useQuery({
    queryKey: ['organizer', 'trash', page],
    queryFn: ({ signal }) =>
      apiFetch<Page<EventItem>>('/events/', {
        query: { include_inactive: true, is_active: false, page },
        signal,
      }),
    placeholderData: keepPreviousData,
  })
}

// Owner or admin; only cancelled or completed events (the backend says why not)
export function useMoveToTrash() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/events/${id}/`, { method: 'DELETE' }),
    onSuccess: (_, id) => {
      // Its public page is gone for everyone but its buyers
      client.removeQueries({ queryKey: ['events', 'detail', id] })
      refreshEventLists(client)
    },
  })
}

export function useRestoreEvent() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<EventItem>(`/events/${id}/restore/`, { method: 'POST' }),
    onSuccess: (event) => refreshEvent(client, event),
  })
}

// Refused (409) while bookings, tickets or payouts point at the event
export function useDeleteForever() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/events/${id}/`, {
        method: 'DELETE',
        query: { hard: true },
      }),
    onSuccess: (_, id) => {
      client.removeQueries({ queryKey: ['events', 'detail', id] })
      refreshEventLists(client)
    },
  })
}

// ---------- sales ----------

export interface EventSales {
  tickets_sold: number
  // Decimal strings, USD
  gross_revenue: string
  tickets: {
    ticket_id: string
    ticket_code: string
    // What the buyer paid, net of partial refunds
    amount: string
    refunded: string
    status: 'confirmed' | 'refunded'
  }[]
}

export function useEventSales(id: string | undefined) {
  return useQuery({
    queryKey: ['organizer', 'sales', id],
    queryFn: ({ signal }) =>
      apiFetch<EventSales>(`/organizer/events/${id}/sales/`, { signal }),
    enabled: isUuid(id),
    retry: false,
  })
}

// ---------- payouts ----------

export type PayoutStatus = 'pending' | 'processing' | 'settled' | 'failed'

export interface Payout {
  id: string
  event_id: string
  event_title: string
  // Decimal strings, USD
  gross_revenue: string
  platform_fee: string
  net_amount: string
  status: PayoutStatus
  settled_at: string | null
  created_at: string
}

export const PAYOUT_STATUS: Record<
  PayoutStatus,
  { label: string; tone: StatusTone }
> = {
  pending: { label: 'Pending', tone: 'neutral' },
  processing: { label: 'Processing', tone: 'warning' },
  settled: { label: 'Settled', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
}

// Organizers see their own payouts; admins see everyone's
export function usePayouts(scope: 'organizer' | 'admin') {
  return useQuery({
    queryKey: [scope, 'payouts'],
    queryFn: ({ signal }) =>
      apiFetch<Page<Payout>>(`/${scope}/payouts/`, { signal }),
  })
}

// Completed events that sold tickets and have no payout yet. Admins see all
// of them ("ready to pay out"); organizers see their own ("upcoming").
export interface AwaitingPayout {
  event_id: string
  event_title: string
  organizer_name: string
  venue_name: string
  completed_at: string
  payout_available_at: string
  // True once the 24-hour wait after completion is over
  eligible: boolean
  // Decimal strings, USD
  gross_revenue: string
  platform_fee: string
  net_amount: string
}

export function useAwaitingPayouts(scope: 'organizer' | 'admin') {
  return useQuery({
    queryKey: [scope, 'payouts', 'awaiting'],
    queryFn: ({ signal }) =>
      apiFetch<Page<AwaitingPayout>>(
        scope === 'admin'
          ? '/admin/payouts/ready/'
          : '/organizer/payouts/upcoming/',
        { signal },
      ),
  })
}

// Admin only: creates the payout and starts settling it in one step
export function usePayOut() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (eventId: string) =>
      apiFetch<Payout>(`/admin/events/${eventId}/payouts/`, { method: 'POST' }),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'payouts'] })
    },
  })
}

// Admin only: refund every buyer a share of what they paid (an event that
// was cut short). Allowed once per event, before the payout.
export function useRefundPart() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ eventId, percent }: { eventId: string; percent: number }) =>
      apiFetch<{ refunds: number; amount: string }>(
        `/admin/events/${eventId}/partial-refunds/`,
        { method: 'POST', body: { percent } },
      ),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin', 'payouts'] })
    },
  })
}

// ---------- venue requests ----------

export type VenueRequestStatus = 'pending' | 'fulfilled' | 'rejected'

export interface VenueRequest {
  id: string
  requested_by: string
  venue_name: string
  city: string
  notes: string
  status: VenueRequestStatus
  admin_notes: string
  created_at: string
  reviewed_at: string | null
}

export const VENUE_REQUEST_STATUS: Record<
  VenueRequestStatus,
  { label: string; tone: StatusTone }
> = {
  pending: { label: 'Waiting for review', tone: 'warning' },
  fulfilled: { label: 'Venue added', tone: 'success' },
  rejected: { label: 'Declined', tone: 'danger' },
}

// The same endpoint serves both roles: an admin gets every request
export function useVenueRequests() {
  return useQuery({
    queryKey: ['venue-requests'],
    queryFn: ({ signal }) =>
      apiFetch<Page<VenueRequest>>('/venues/requests/', { signal }),
  })
}

export function useCreateVenueRequest() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: Pick<VenueRequest, 'venue_name' | 'city' | 'notes'>) =>
      apiFetch<VenueRequest>('/venues/requests/', { method: 'POST', body }),
    onSuccess: () =>
      void client.invalidateQueries({ queryKey: ['venue-requests'] }),
  })
}
