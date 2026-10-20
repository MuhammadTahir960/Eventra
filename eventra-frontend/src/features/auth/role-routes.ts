import type { Role } from './auth-store'

// Where each role lands after login
export const ROLE_HOME: Record<Role, string> = {
  attendee: '/events',
  organizer: '/organizer/events',
  admin: '/admin/moderation',
}

export interface NavItem {
  to: string
  label: string
  // Match only this exact path (so "My events" isn't active on "Create event")
  end?: boolean
}

// Sidebar links of the workspace shell. Server permissions remain the real gate.
export const WORKSPACE_NAV: Record<'organizer' | 'admin', NavItem[]> = {
  organizer: [
    { to: '/organizer/events', label: 'My events', end: true },
    { to: '/organizer/events/new', label: 'Create event' },
    { to: '/organizer/payouts', label: 'Payouts' },
    { to: '/organizer/venue-requests', label: 'Venue requests' },
  ],
  admin: [
    { to: '/admin/moderation', label: 'Moderation' },
    { to: '/admin/events', label: 'Events' },
    { to: '/admin/users', label: 'Users' },
    { to: '/admin/payouts', label: 'Payouts' },
    { to: '/admin/venues', label: 'Venues' },
    { to: '/admin/sports', label: 'Sports' },
    { to: '/admin/venue-requests', label: 'Venue requests' },
    { to: '/organizer/events/new', label: 'Create event' },
  ],
}

export const WORKSPACE_LABEL: Record<'organizer' | 'admin', string> = {
  organizer: 'Organizer workspace',
  admin: 'Admin workspace',
}
