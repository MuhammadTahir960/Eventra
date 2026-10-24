import { Link, NavLink, Outlet } from 'react-router-dom'
import { AccountMenu } from '@/components/AccountMenu'
import { OfflineBanner } from '@/components/OfflineBanner'
import { Logo } from '@/components/Logo'
import { SkipLink } from '@/components/SkipLink'
import { useAuth } from '@/features/auth/auth-store'
import { WORKSPACE_LABEL, WORKSPACE_NAV } from '@/features/auth/role-routes'
import { cn } from '@/lib/utils'

// Back office for organizers and admins: sidebar on desktop, a scrolling tab
// row on phones. Pages inside are already role-guarded by RequireRole.
export function WorkspaceShell() {
  const { user } = useAuth()
  if (!user || user.role === 'attendee') return null
  const role = user.role
  const nav = WORKSPACE_NAV[role]

  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <OfflineBanner />

      <div className="flex flex-1 flex-col lg:flex-row">
        <aside className="border-b border-border bg-card lg:w-60 lg:shrink-0 lg:border-r lg:border-b-0">
          <div className="lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col">
            <div className="gutter flex h-16 items-center justify-between lg:px-5">
              <Link to="/" aria-label="Eventra home">
                <Logo size={24} />
              </Link>
              <div className="lg:hidden">
                <AccountMenu user={user} />
              </div>
            </div>

            <p className="hidden px-5 pt-2 pb-2 text-[13px] text-muted-foreground lg:block">
              {WORKSPACE_LABEL[role]}
            </p>
            <nav
              aria-label={WORKSPACE_LABEL[role]}
              className="gutter flex gap-1 overflow-x-auto pb-2 lg:flex-col lg:overflow-visible lg:px-3 lg:pb-0"
            >
              {nav.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={({ isActive }) =>
                    cn(
                      'shrink-0 rounded-md px-3 py-2 text-sm whitespace-nowrap transition-colors',
                      isActive
                        ? 'bg-muted font-medium text-foreground'
                        : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                    )
                  }
                >
                  {item.label}
                </NavLink>
              ))}
            </nav>

            <div className="mt-auto hidden border-t border-border p-3 lg:block">
              <Link
                to="/"
                className="mb-1 block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-muted hover:text-foreground"
              >
                Back to the site
              </Link>
              <AccountMenu user={user} />
            </div>
          </div>
        </aside>

        <main id="main" tabIndex={-1} className="min-w-0 flex-1 outline-none">
          <div className="gutter mx-auto max-w-[1120px] py-8 lg:py-10">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
