import { useSyncExternalStore } from 'react'

// Roles match the backend's `role` values. The server re-checks the role on
// every request, so this is only used to choose which screens to show.
export type Role = 'attendee' | 'organizer' | 'admin'

// Shape of GET /auth/me/ (the backend's UserSerializer)
export interface SessionUser {
  id: string
  email: string
  role: Role
  first_name: string
  last_name: string
  gender: 'male' | 'female' | 'other' | ''
  // Static asset key derived from gender; null when gender was never set
  avatar: string | null
}

interface AuthState {
  user: SessionUser | null
  // Access token: memory only (15 minute lifetime)
  accessToken: string | null
  // Refresh token: kept in sessionStorage so a reload doesn't sign you out.
  // Trade-off: readable by any script on the page, so XSS could steal it.
  // It is dropped when the tab closes, and the backend rotates it on use.
  refreshToken: string | null
  // 'restoring' while a saved session is being re-validated after a reload
  status: 'restoring' | 'ready'
}

const REFRESH_KEY = 'eventra-refresh'

function readSavedRefreshToken(): string | null {
  try {
    return sessionStorage.getItem(REFRESH_KEY)
  } catch {
    return null
  }
}

function saveRefreshToken(token: string | null) {
  try {
    if (token) sessionStorage.setItem(REFRESH_KEY, token)
    else sessionStorage.removeItem(REFRESH_KEY)
  } catch {
    // Storage can be blocked; the session then just lasts until reload
  }
}

const savedRefresh = readSavedRefreshToken()
let state: AuthState = {
  user: null,
  accessToken: null,
  refreshToken: savedRefresh,
  status: savedRefresh ? 'restoring' : 'ready',
}
const listeners = new Set<() => void>()

function update(next: AuthState) {
  state = next
  listeners.forEach((listener) => listener())
}

export const authStore = {
  getState: () => state,
  subscribe(listener: () => void) {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  // After login or a refresh: new token pair, profile not loaded yet
  setTokens(accessToken: string, refreshToken: string) {
    saveRefreshToken(refreshToken)
    update({ ...state, accessToken, refreshToken })
  },
  // Fully signed in
  setSession(user: SessionUser, accessToken: string, refreshToken: string) {
    saveRefreshToken(refreshToken)
    update({ user, accessToken, refreshToken, status: 'ready' })
  },
  setUser(user: SessionUser) {
    update({ ...state, user })
  },
  markReady() {
    update({ ...state, status: 'ready' })
  },
  clear() {
    saveRefreshToken(null)
    update({
      user: null,
      accessToken: null,
      refreshToken: null,
      status: 'ready',
    })
  },
}

export function useAuth(): AuthState {
  return useSyncExternalStore(authStore.subscribe, authStore.getState)
}
