import { apiFetch } from '@/lib/api-client'
import type { Role, SessionUser } from './auth-store'

// POST /auth/login/ returns tokens and role only, never the profile
export interface LoginResponse {
  access: string
  refresh: string
  role: Role
}

// POST /auth/refresh/ rotates the refresh token on every call
export interface RefreshResponse {
  access: string
  refresh?: string
}

export interface RegisterPayload {
  email: string
  password: string
  first_name: string
  last_name: string
  gender: 'male' | 'female' | 'other'
  // The backend rejects 'admin'; only these two can be chosen
  role: 'attendee' | 'organizer'
}

export const authApi = {
  login: (email: string, password: string) =>
    apiFetch<LoginResponse>('/auth/login/', {
      method: 'POST',
      body: { email, password },
      auth: false,
    }),

  refresh: (refresh: string) =>
    apiFetch<RefreshResponse>('/auth/refresh/', {
      method: 'POST',
      body: { refresh },
      auth: false,
    }),

  logout: (refresh: string) =>
    apiFetch<void>('/auth/logout/', { method: 'POST', body: { refresh } }),

  me: () => apiFetch<SessionUser>('/auth/me/'),

  register: (payload: RegisterPayload) =>
    apiFetch<Omit<SessionUser, 'avatar'>>('/auth/register/', {
      method: 'POST',
      body: payload,
      auth: false,
    }),

  verifyEmail: (token: string) =>
    apiFetch<{ detail: string; email: string }>('/auth/verify-email/', {
      query: { token },
      auth: false,
    }),

  requestPasswordReset: (email: string) =>
    apiFetch<{ detail: string }>('/auth/password-reset/', {
      method: 'POST',
      body: { email },
      auth: false,
    }),

  confirmPasswordReset: (token: string, newPassword: string) =>
    apiFetch<{ detail: string }>('/auth/password-reset/confirm/', {
      method: 'POST',
      body: { token, new_password: newPassword },
      auth: false,
    }),
}
