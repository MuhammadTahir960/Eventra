import { isRouteErrorResponse, useRouteError } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Logo } from '@/components/Logo'
import { Button } from '@/components/ui/button'
import { usePageTitle } from '@/lib/use-page-title'

// After a deploy, an open tab still asks for the old page chunks, which no
// longer exist. Browsers word that failure differently.
function isStaleChunk(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /dynamically imported module|Importing a module script failed|error loading dynamically imported module/i.test(
    message,
  )
}

// Replaces React Router's developer error screen. It renders outside the
// shells (one of them may be what crashed), so it brings its own chrome.
export function RouteError() {
  const error = useRouteError()
  const stale = isStaleChunk(error)
  const notFound = isRouteErrorResponse(error) && error.status === 404
  usePageTitle(
    stale
      ? 'Eventra has been updated'
      : notFound
        ? 'Page not found'
        : 'Something went wrong',
  )

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="gutter mx-auto flex h-16 w-full max-w-[1200px] items-center">
        <a href="/" aria-label="Eventra home">
          <Logo size={26} />
        </a>
      </header>
      <main id="main" className="gutter mx-auto w-full max-w-[1200px] pt-16">
        <EmptyState
          title={
            stale
              ? 'Eventra has been updated'
              : notFound
                ? 'Page not found'
                : 'Something went wrong'
          }
          body={
            stale
              ? 'Reload the page to get the latest version. Nothing you saved is lost.'
              : notFound
                ? "That page doesn't exist or has moved."
                : 'The page hit an unexpected error. Reload to try again, or go back to the home page.'
          }
          action={
            <div className="flex flex-wrap justify-center gap-2">
              {!notFound && (
                <Button variant="ink" onClick={() => window.location.reload()}>
                  Reload the page
                </Button>
              )}
              {/* A full page load, not a router link: the router may be what failed */}
              <a
                href="/"
                className="inline-flex h-10 items-center rounded-md px-4 text-sm font-medium hover:bg-muted"
              >
                Go to the home page
              </a>
            </div>
          }
        />
      </main>
    </div>
  )
}
