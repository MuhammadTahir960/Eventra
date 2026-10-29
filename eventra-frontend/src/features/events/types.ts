export type EventType = 'general' | 'sports_match'

export type EventStatus =
  'pending_approval' | 'approved' | 'rejected' | 'cancelled' | 'completed'

// Shape of the backend's EventSerializer. Relations are bare IDs: names and
// photos come from the catalog lists. `rejection_reason` is only sent to the
// event's own organizer and to admins.
export interface EventItem {
  id: string
  organizer: string
  venue: string | null
  category: string | null
  league: string | null
  home_team: string | null
  away_team: string | null
  title: string
  // Used only for the seat-map WebSocket URL; pages are addressed by `id`
  slug: string
  description: string
  event_type: EventType
  status: EventStatus
  rejection_reason?: string
  is_seated: boolean
  start_datetime: string
  end_datetime: string
  // Set when the event is marked completed; payouts open 24h later
  completed_at: string | null
  is_active: boolean
  created_at: string
  updated_at: string
}

// GET /events/{id}/ticket-tiers/ returns a plain array (not paginated)
export interface TicketTier {
  id: string
  event: string
  name: string
  // Decimal string, e.g. "45.00"
  price: string
  created_at: string
}
