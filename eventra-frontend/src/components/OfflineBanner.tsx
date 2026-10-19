import { useSyncExternalStore } from 'react'

function subscribe(onChange: () => void) {
  window.addEventListener('online', onChange)
  window.addEventListener('offline', onChange)
  return () => {
    window.removeEventListener('online', onChange)
    window.removeEventListener('offline', onChange)
  }
}

// Shown at the top of the page while the browser reports no connection. Seat
// status is live data, so stale availability is the thing to warn about.
export function OfflineBanner() {
  const online = useSyncExternalStore(subscribe, () => navigator.onLine)
  if (online) return null
  return (
    <div
      role="status"
      className="gutter bg-warning-bg py-2 text-center text-[13px] text-warning"
    >
      <strong className="font-semibold">You're offline.</strong> Seat
      availability and prices may be out of date until you reconnect.
    </div>
  )
}
