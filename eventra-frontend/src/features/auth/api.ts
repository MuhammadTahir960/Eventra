import { apiFetch } from '@/lib/api-client'
import type { PayoutAccount, Role, SessionUser } from './auth-store'

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
  // Cloudflare Turnstile token, checked by the backend before anything else
  captcha_token: string
  // Organizers only. The number is never sent: only the token Eventra issued
  payout_account?: Pick<
    PayoutAccount,
    'method' | 'provider' | 'holder_name'
  > & {
    number_token: string
  }
}

// A new account number, shown locked on the sign-up form before the account exists
export interface IssuedAccountNumber {
  number: string
  token: string
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

  issueAccountNumber: () =>
    apiFetch<IssuedAccountNumber>('/payout-account-numbers/', {
      method: 'POST',
      auth: false,
    }),

  register: (payload: RegisterPayload) =>
    // The same answer whether or not the email already had an account
    apiFetch<{ email: string }>('/auth/register/', {
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
