import type { QueryClient } from '@tanstack/react-query'
import { authStore } from '@/features/auth/auth-store'
import { clearCheckoutContexts } from '@/features/bookings/api'

// Query keys don't include the user, so when someone signs out (or another
// account signs in on the same tab) drop everything the previous user loaded
export function clearCacheOnUserChange(client: QueryClient) {
  let lastUserId = authStore.getState().user?.id ?? null
  return authStore.subscribe(() => {
    const userId = authStore.getState().user?.id ?? null
    if (lastUserId !== null && userId !== lastUserId) {
      void client.cancelQueries()
      client.clear()
      clearCheckoutContexts()
    }
    lastUserId = userId
  })
}
