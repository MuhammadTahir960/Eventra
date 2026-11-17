// The backend sends prices as decimal strings ("45.00"). USD only.
const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

export function formatMoney(value: string | number): string {
  const amount = typeof value === 'string' ? Number(value) : value
  return Number.isFinite(amount) ? money.format(amount) : '—'
}

const dateFormatters = new Map<string, Intl.DateTimeFormat>()

// Event times pass the venue's `timeZone`, so everyone sees the time at the
// venue. Without one (sign-up dates, payouts) it is the viewer's own zone.
export function formatDate(
  iso: string,
  options: Intl.DateTimeFormatOptions,
  timeZone?: string,
): string {
  const key = JSON.stringify([options, timeZone])
  let formatter = dateFormatters.get(key)
  if (!formatter) {
    formatter = new Intl.DateTimeFormat(undefined, { ...options, timeZone })
    dateFormatters.set(key, formatter)
  }
  return formatter.format(new Date(iso))
}

const SHORT: Intl.DateTimeFormatOptions = {
  weekday: 'short',
  month: 'short',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
}

const LONG: Intl.DateTimeFormatOptions = {
  weekday: 'long',
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
}

// "Sat, Mar 14, 7:30 PM"
export function formatDateTime(iso: string, timeZone?: string): string {
  return formatDate(iso, SHORT, timeZone)
}

// Same, with the year and time zone name, for detail pages
export function formatDateTimeLong(iso: string, timeZone?: string): string {
  return formatDate(iso, LONG, timeZone)
}

const WALL_CLOCK: Intl.DateTimeFormatOptions = {
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  hourCycle: 'h23',
}

// A moment as the venue's wall-clock time, "2026-11-01T18:30": the value of an
// <input type="datetime-local"> and what the API takes for event times
export function toLocalInput(iso: string, timeZone: string): string {
  const parts: Record<string, string> = {}
  const formatter = new Intl.DateTimeFormat('en-US', {
    ...WALL_CLOCK,
    timeZone,
  })
  for (const part of formatter.formatToParts(new Date(iso)))
    parts[part.type] = part.value
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`
}

// The time at the venue right now, as a Date that compares with
// `new Date(<datetime-local value>)`
export function nowAt(timeZone: string): Date {
  return new Date(toLocalInput(new Date().toISOString(), timeZone))
}

const countryNames = new Intl.DisplayNames(['en'], { type: 'region' })

// The API sends ISO country codes ("PK"); names are never stored
export function countryName(code: string): string {
  return countryNames.of(code) ?? code
}
