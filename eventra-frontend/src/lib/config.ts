// Backend origin. The API has no /api prefix and shares route names with the
// SPA (/events, /bookings), so it can't be proxied by path: it needs its own
// origin, and the backend must list this app's origin in CORS_ALLOWED_ORIGINS.
export const API_BASE_URL: string = (
  import.meta.env.BACKEND_BASE_URL ?? 'http://localhost:8000'
).replace(/\/+$/, '')

// WebSocket origin derived from the API origin (http -> ws, https -> wss)
export const WS_BASE_URL: string = API_BASE_URL.replace(/^http/, 'ws')

// Stripe publishable key (test mode only). The backend exposes no endpoint
// for it, so it has to be provided at build time.
export const STRIPE_PUBLISHABLE_KEY: string =
  import.meta.env.STRIPE_PUBLISHABLE_KEY ?? ''
