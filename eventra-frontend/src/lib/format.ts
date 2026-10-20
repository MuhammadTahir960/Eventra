// The backend sends prices as decimal strings ("45.00"). USD only.
const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'USD',
})

export function formatMoney(value: string | number): string {
  const amount = typeof value === 'string' ? Number(value) : value
  return Number.isFinite(amount) ? money.format(amount) : '—'
}

// "Sat, Mar 14, 7:30 PM" in the viewer's own locale and time zone
export function formatDateTime(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(iso))
}

// Same, with the year and time zone name, for detail pages
export function formatDateTimeLong(iso: string): string {
  return new Intl.DateTimeFormat(undefined, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(new Date(iso))
}
