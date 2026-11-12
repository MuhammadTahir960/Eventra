// Event form rules; they mirror the backend, which still has the final say
export const PRICE_PATTERN = /^\d{1,8}(\.\d{1,2})?$/
// Stripe's smallest card charge; 0 means free
export const MIN_PAID_PRICE = 0.5
// Most tickets one account can buy for an event (the organizer picks)
export const MAX_TICKETS_PER_BUYER = 50
export const DEFAULT_TICKETS_PER_BUYER = 10
export const MAX_LENGTH_DAYS = 14
export const MAX_LEAD_DAYS = 730
