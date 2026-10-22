// How the seat map reacts when its live connection closes.
//
// Close codes come from the backend's SeatConsumer:
//   4401 ticket invalid/expired/used -> fetch a fresh ticket and retry
//   4404 event not visible to this user -> retrying can never help
//   4429 too many connection attempts -> back off for much longer
//   4400 unexpected message           -> just reconnect
// Anything else (network drop, server restart) is a normal retry.

export type ReconnectAction = 'stop' | 'retry' | 'slow'

export function decideReconnect(code: number): ReconnectAction {
  if (code === 4404) return 'stop'
  if (code === 4429) return 'slow'
  return 'retry'
}

const BASE_DELAY_MS = 1_000
const MAX_DELAY_MS = 15_000
const SLOW_DELAY_MS = 30_000

// Exponential backoff (1s, 2s, 4s ... capped) plus up to 25% jitter so many
// clients that lost the connection together don't all return together.
export function reconnectDelay(
  attempt: number,
  action: Exclude<ReconnectAction, 'stop'> = 'retry',
  random: () => number = Math.random,
): number {
  const base =
    action === 'slow'
      ? SLOW_DELAY_MS
      : Math.min(BASE_DELAY_MS * 2 ** Math.max(attempt, 0), MAX_DELAY_MS)
  return Math.round(base * (1 + random() * 0.25))
}
