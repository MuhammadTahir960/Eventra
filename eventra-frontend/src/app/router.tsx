import type { ComponentType } from 'react'
import { createBrowserRouter } from 'react-router-dom'
import { AppShell } from './AppShell'
import { RootLayout } from './RootLayout'
import { RouteError } from './RouteError'
import { RequireRole } from '@/features/auth/RequireRole'

// Every page is code-split so the first load only ships the shell.
const page =
  <T,>(load: () => Promise<T>, pick: (module: T) => ComponentType) =>
  async () => ({ Component: pick(await load()) })

const loadHome = page(
  () => import('./HomePage'),
  (m) => m.HomePage,
)
const loadNotFound = page(
  () => import('./NotFoundPage'),
  (m) => m.NotFoundPage,
)
const loadLogin = page(
  () => import('@/features/auth/pages/LoginPage'),
  (m) => m.LoginPage,
)
const loadRegister = page(
  () => import('@/features/auth/pages/RegisterPage'),
  (m) => m.RegisterPage,
)
const loadVerifyEmail = page(
  () => import('@/features/auth/pages/VerifyEmailPage'),
  (m) => m.VerifyEmailPage,
)
const loadForgotPassword = page(
  () => import('@/features/auth/pages/ForgotPasswordPage'),
  (m) => m.ForgotPasswordPage,
)
const loadResetPassword = page(
  () => import('@/features/auth/pages/ResetPasswordPage'),
  (m) => m.ResetPasswordPage,
)
const loadEvents = page(
  () => import('@/features/events/pages/EventsPage'),
  (m) => m.EventsPage,
)
const loadSports = page(
  () => import('@/features/events/pages/SportsPage'),
  (m) => m.SportsPage,
)
const loadEventDetail = page(
  () => import('@/features/events/pages/EventDetailPage'),
  (m) => m.EventDetailPage,
)
const loadProfile = page(
  () => import('@/features/auth/pages/ProfilePage'),
  (m) => m.ProfilePage,
)

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    // Branded error page instead of React Router's developer screen
    errorElement: <RouteError />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, lazy: loadHome },

          // Public
          { path: 'login', lazy: loadLogin },
          { path: 'register', lazy: loadRegister },
          { path: 'verify-email', lazy: loadVerifyEmail },
          { path: 'forgot-password', lazy: loadForgotPassword },
          { path: 'reset-password', lazy: loadResetPassword },
          { path: 'events', lazy: loadEvents },
          { path: 'sports', lazy: loadSports },
          // Events are addressed by id; the slug is only for the seat-map socket
          { path: 'events/:id', lazy: loadEventDetail },

          // Any signed-in role
          {
            element: <RequireRole roles={['attendee', 'organizer', 'admin']} />,
            children: [{ path: 'profile', lazy: loadProfile }],
          },

          { path: '*', lazy: loadNotFound },
        ],
      },
    ],
  },
])
