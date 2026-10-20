import { ApiError, configureApiAuth } from '@/lib/api-client'
import { authApi } from './api'
import { authStore, type Role } from './auth-store'

// One refresh at a time: if several requests hit an expired token together
// they share this promise. Needed because the backend rotates the refresh
// token, so a second concurrent refresh would use an already-used token.
let refreshInFlight: Promise<string | null> | null = null

async function performRefresh(): Promise<string | null> {
  const refreshToken = authStore.getState().refreshToken
  if (!refreshToken) return null

  try {
    const data = await authApi.refresh(refreshToken)
    // Rotation returns a new refresh token; keep the old one if absent
    authStore.setTokens(data.access, data.refresh ?? refreshToken)
    return data.access
  } catch (error) {
    // Only a rejected token ends the session. A network blip shouldn't.
    if (error instanceof ApiError && [400, 401].includes(error.status)) {
      authStore.clear()
    }
    return null
  }
}

export function refreshTokens(): Promise<string | null> {
  refreshInFlight ??= performRefresh().finally(() => {
    refreshInFlight = null
  })
  return refreshInFlight
}

// Wire the API client to this session (runs once, when this module loads)
configureApiAuth({
  getAccessToken: () => authStore.getState().accessToken,
  refreshAccessToken: refreshTokens,
})

// After a page reload: re-validate the saved refresh token and load the profile
let restorePromise: Promise<void> | null = null

export function restoreSession(): Promise<void> {
  restorePromise ??= (async () => {
    if (authStore.getState().status !== 'restoring') return
    try {
      const access = await refreshTokens()
      if (access) {
        const user = await authApi.me()
        authStore.setUser(user)
      }
    } catch {
      // Profile load failed: treat as signed out rather than half-signed-in
      authStore.clear()
    } finally {
      authStore.markReady()
    }
  })()
  return restorePromise
}

// Login gives tokens + role; the profile needs a second call
export async function signIn(email: string, password: string): Promise<Role> {
  const { access, refresh, role } = await authApi.login(email, password)
  authStore.setTokens(access, refresh)
  try {
    const user = await authApi.me()
    authStore.setSession(user, access, refresh)
    return role
  } catch (error) {
    authStore.clear()
    throw error
  }
}

export async function signOut(): Promise<void> {
  const refreshToken = authStore.getState().refreshToken
  try {
    // Blacklists the refresh token server-side
    if (refreshToken) await authApi.logout(refreshToken)
  } catch {
    // Offline or already expired: still sign out locally
  } finally {
    authStore.clear()
  }
}
