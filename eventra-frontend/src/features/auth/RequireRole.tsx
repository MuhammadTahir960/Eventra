import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { ButtonLink } from '@/components/ui/button-link'
import { useAuth, type Role } from './auth-store'
import { ROLE_HOME } from './role-routes'

// Route guard. This is a UX convenience only: every API call is still
// authorised by the server, so a forged client state gains nothing.
export function RequireRole({ roles }: { roles: Role[] }) {
  const { user, status } = useAuth()
  const location = useLocation()

  // Reload in progress: wait for the saved session to be re-checked instead
  // of bouncing a signed-in user to the login page
  if (status === 'restoring') {
    return (
      <p role="status" className="p-8 text-center text-muted-foreground">
        Loading…
      </p>
    )
  }

  // Not signed in: send to login and remember where they were headed
  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  // Signed in with the wrong role: explain instead of silently redirecting
  if (!roles.includes(user.role)) {
    return (
      <div role="alert" className="gutter mx-auto max-w-[1200px] pt-16">
        <EmptyState
          title="Access restricted"
          body="Your account type can't open this page."
          action={
            <ButtonLink variant="ink" to={ROLE_HOME[user.role]}>
              Go to your home page
            </ButtonLink>
          }
        />
      </div>
    )
  }

  return <Outlet />
}
