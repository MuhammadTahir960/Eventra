import { HugeiconsIcon } from '@hugeicons/react'
import { Search01Icon } from '@hugeicons/core-free-icons'
import { useState, type FormEvent } from 'react'
import {
  Link,
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from 'react-router-dom'
import { AccountMenu } from '@/components/AccountMenu'
import { OfflineBanner } from '@/components/OfflineBanner'
import { Logo } from '@/components/Logo'
import { SkipLink } from '@/components/SkipLink'
import { ButtonLink } from '@/components/ui/button-link'
import { useAuth } from '@/features/auth/auth-store'
import { cn } from '@/lib/utils'

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  cn(
    'rounded-md px-2.5 py-2 text-sm transition-colors hover:text-foreground',
    isActive ? 'font-medium text-foreground' : 'text-muted-foreground',
  )

function HeaderSearch() {
  const navigate = useNavigate()
  const [params] = useSearchParams()
  const { pathname } = useLocation()
  // Mirror the events page query so the box shows what is being searched
  const [value, setValue] = useState(
    pathname === '/events' ? (params.get('q') ?? '') : '',
  )

  function onSubmit(event: FormEvent) {
    event.preventDefault()
    const q = value.trim()
    navigate(q ? `/events?q=${encodeURIComponent(q)}` : '/events')
  }

  return (
    <form
      role="search"
      onSubmit={onSubmit}
      className="relative hidden md:block"
    >
      <label htmlFor="header-search" className="sr-only">
        Search events
      </label>
      <HugeiconsIcon
        icon={Search01Icon}
        size={16}
        aria-hidden
        className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-muted-foreground"
      />
      <input
        id="header-search"
        type="search"
        value={value}
        maxLength={100}
        onChange={(event) => setValue(event.target.value)}
        placeholder="Search events, venues, teams…"
        className="h-9 w-64 rounded-full border border-border bg-card pr-3 pl-9 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring lg:w-72"
      />
    </form>
  )
}

export function AppShell() {
  const { user, status } = useAuth()
  // The events page has its own search box
  const showSearch = useLocation().pathname !== '/events'

  return (
    <div className="flex min-h-dvh flex-col">
      <SkipLink />
      <OfflineBanner />

      <header className="sticky top-[env(safe-area-inset-top,0px)] z-30 border-b border-border bg-paper/90 backdrop-blur-md">
        <div className="gutter mx-auto flex h-16 max-w-[1200px] items-center gap-2 sm:gap-6">
          <Link to="/" aria-label="Eventra home" className="mr-1 shrink-0">
            <Logo
              size={26}
              className="max-[359px]:[&>span:last-child]:hidden"
            />
          </Link>

          <nav aria-label="Main" className="flex items-center">
            <NavLink to="/events" end className={navLinkClass}>
              Events
            </NavLink>
            <NavLink to="/sports" className={navLinkClass}>
              Sports
            </NavLink>
          </nav>

          <div className="ml-auto flex items-center gap-2">
            {showSearch && <HeaderSearch />}
            <ButtonLink
              variant="ghost"
              size="icon"
              className={cn('md:hidden', !showSearch && 'hidden')}
              aria-label="Search events"
              to="/events?focus=search"
            >
              <HugeiconsIcon icon={Search01Icon} size={18} />
            </ButtonLink>

            {/* Avoid flashing "Sign in" while a saved session is restored */}
            {status === 'restoring' ? (
              <span className="size-10" aria-hidden />
            ) : user ? (
              <AccountMenu user={user} />
            ) : (
              <>
                <ButtonLink
                  variant="ghost"
                  className="hidden sm:inline-flex"
                  to="/login"
                >
                  Sign in
                </ButtonLink>
                <ButtonLink variant="ink" to="/login" className="sm:hidden">
                  Sign in
                </ButtonLink>
                <ButtonLink
                  variant="ink"
                  className="hidden sm:inline-flex"
                  to="/register"
                >
                  Create account
                </ButtonLink>
              </>
            )}
          </div>
        </div>
      </header>

      {/* tabIndex lets the skip link move focus here */}
      <main id="main" tabIndex={-1} className="flex-1 outline-none">
        <Outlet />
      </main>

      <footer className="mt-24 border-t border-border">
        <div className="gutter mx-auto flex max-w-[1200px] flex-col gap-6 py-10 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-2">
            <Logo size={22} />
            <p className="max-w-sm text-[13px] text-muted-foreground">
              Concerts, theatre and live sport, with seats you pick yourself.
            </p>
          </div>
          <nav
            aria-label="Footer"
            className="flex gap-5 text-sm text-muted-foreground"
          >
            <Link to="/events" className="hover:text-foreground">
              Events
            </Link>
            <Link to="/sports" className="hover:text-foreground">
              Sports
            </Link>
            {!user && (
              <Link
                to="/register?role=organizer"
                className="hover:text-foreground"
              >
                Sell tickets
              </Link>
            )}
          </nav>
        </div>
      </footer>
    </div>
  )
}
