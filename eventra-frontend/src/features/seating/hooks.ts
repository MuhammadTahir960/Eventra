import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { WS_BASE_URL } from '@/lib/config'
import { apiFetch } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import { seatingApi } from './api'
import type { LayoutSeatInput } from './layout/layout'
import { applySeatMessage, parseSeatMessage } from './seat-state'
import { decideReconnect, reconnectDelay } from './socket-policy'
import type { EventSeat } from './types'

// GET /venues/{id}/seats/ is a plain array (not paginated) and needs an
// organizer or admin login: it is the venue's reusable physical seat map.
export function useVenueTemplate(venueId: string | undefined) {
  return useQuery({
    queryKey: ['venues', 'template', venueId],
    queryFn: ({ signal }) =>
      apiFetch<LayoutSeatInput[]>(`/venues/${venueId}/seats/`, { signal }),
    enabled: isUuid(venueId),
    // A venue's seat map rarely changes while someone is creating an event
    staleTime: 5 * 60_000,
  })
}

export type ConnectionState =
  | 'connecting'
  | 'live'
  | 'reconnecting'
  // Live updates are off; the map refreshes by polling instead
  | 'polling'

// After this many failed attempts in a row we stop hammering the socket
const MAX_FAILED_ATTEMPTS = 6
const POLL_INTERVAL_MS = 15_000

// An event's seat map: loaded over REST, then kept live over the WebSocket.
// Every socket message is written into the query cache, so the page just
// reads `seats` and re-renders. If the socket can't connect, the map falls
// back to refreshing every 15 seconds.
export function useLiveSeats(
  eventId: string | undefined,
  slug: string | undefined,
) {
  const queryClient = useQueryClient()
  const [connection, setConnection] = useState<ConnectionState>('connecting')
  const queryKey = ['seats', eventId]

  const seats = useQuery({
    queryKey,
    queryFn: ({ signal }) => seatingApi.getSeats(eventId ?? '', signal),
    enabled: isUuid(eventId),
    refetchInterval: connection === 'polling' ? POLL_INTERVAL_MS : false,
  })

  useEffect(() => {
    if (!slug || !isUuid(eventId)) return
    const key = ['seats', eventId]

    let cancelled = false
    let socket: WebSocket | null = null
    let timer: ReturnType<typeof setTimeout> | undefined
    let failedAttempts = 0

    function scheduleRetry(action: 'retry' | 'slow') {
      failedAttempts += 1
      if (failedAttempts >= MAX_FAILED_ATTEMPTS) {
        // The browser reports a refused handshake the same way as a network
        // drop, so repeated failures are treated as "no live updates here".
        setConnection('polling')
        return
      }
      setConnection('reconnecting')
      timer = setTimeout(
        () => void connect(),
        reconnectDelay(failedAttempts - 1, action),
      )
    }

    async function connect() {
      if (cancelled) return
      let ticket: string
      try {
        // Single use and valid for 30 seconds, so every connect needs a new one
        ticket = (await seatingApi.getSocketTicket()).ticket
      } catch {
        scheduleRetry('retry')
        return
      }
      if (cancelled) return

      const ws = new WebSocket(
        `${WS_BASE_URL}/ws/seats/${encodeURIComponent(slug ?? '')}/?ticket=${encodeURIComponent(ticket)}`,
      )
      socket = ws

      ws.onopen = () => {
        failedAttempts = 0
        setConnection('live')
      }
      ws.onmessage = (event: MessageEvent) => {
        if (typeof event.data !== 'string') return
        const message = parseSeatMessage(event.data)
        if (message) {
          queryClient.setQueryData<EventSeat[]>(key, (current) =>
            applySeatMessage(current, message),
          )
        }
      }
      ws.onclose = (event: CloseEvent) => {
        if (cancelled) return
        const action = decideReconnect(event.code)
        if (action === 'stop') {
          setConnection('polling')
          return
        }
        scheduleRetry(action)
      }
    }

    void connect()
    return () => {
      cancelled = true
      clearTimeout(timer)
      socket?.close()
    }
  }, [eventId, slug, queryClient])

  return { seats, connection }
}
