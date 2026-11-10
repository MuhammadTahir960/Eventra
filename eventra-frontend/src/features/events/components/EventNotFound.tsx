import { EmptyState } from '@/components/EmptyState'
import { ButtonLink } from '@/components/ui/button-link'

export function EventNotFound() {
  return (
    <div className="gutter mx-auto max-w-[1200px] pt-16">
      <EmptyState
        title="Event not found"
        body="It may have been removed, or the link is wrong."
        action={
          <ButtonLink variant="ink" to="/events">
            Browse events
          </ButtonLink>
        }
      />
    </div>
  )
}
