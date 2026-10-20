import { EmptyState } from '@/components/EmptyState'
import { ButtonLink } from '@/components/ui/button-link'
import { usePageTitle } from '@/lib/use-page-title'

export function NotFoundPage() {
  usePageTitle('Page not found')
  return (
    <div className="gutter mx-auto max-w-[1200px] pt-16">
      <EmptyState
        title="Page not found"
        body="That page doesn't exist or has moved."
        action={
          <ButtonLink variant="ink" to="/events">
            Browse events
          </ButtonLink>
        }
      />
    </div>
  )
}
