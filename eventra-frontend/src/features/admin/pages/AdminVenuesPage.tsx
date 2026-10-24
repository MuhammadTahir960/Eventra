import { Link } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { ButtonLink } from '@/components/ui/button-link'
import { useVenues } from '@/features/catalog/hooks'
import { ImageWithFallback } from '@/components/ImageWithFallback'
import { usePageTitle } from '@/lib/use-page-title'

function NoPhoto({ text }: { text: string }) {
  return (
    <span className="grid size-full place-items-center text-sm text-muted-foreground">
      {text}
    </span>
  )
}

export function AdminVenuesPage() {
  usePageTitle('Venues')
  const venues = useVenues()
  const list = venues.data?.list ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Venues"
        description="Venue photos appear on every event held there, so a good photo matters."
        actions={
          <ButtonLink variant="ink" to="/admin/venues/new">
            Add venue
          </ButtonLink>
        }
      />
      {venues.isError ? (
        <Notice tone="error">{venues.error.message}</Notice>
      ) : venues.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading venues"
          className="h-64 animate-pulse rounded-lg bg-muted"
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No venues yet"
          body="Add a venue and its seat map so organizers can list events there."
        />
      ) : (
        <ul className="grid gap-x-6 gap-y-8 sm:grid-cols-2 lg:grid-cols-3">
          {list.map((venue) => (
            <li key={venue.id} className="group relative flex flex-col gap-3">
              <div className="aspect-[4/3] overflow-hidden rounded-lg border border-border bg-muted">
                {venue.photo ? (
                  <ImageWithFallback
                    src={venue.photo}
                    alt=""
                    loading="lazy"
                    fallback={<NoPhoto text="Photo missing, upload it again" />}
                    className="size-full object-cover"
                  />
                ) : (
                  <NoPhoto text="No photo yet" />
                )}
              </div>
              <div>
                <h2 className="font-display text-[24px] leading-tight">
                  <Link
                    to={`/admin/venues/${venue.id}`}
                    className="underline-offset-4 group-hover:underline after:absolute after:inset-0"
                  >
                    {venue.name}
                  </Link>
                </h2>
                <p className="tabular text-sm text-muted-foreground">
                  {venue.city}, capacity {venue.capacity.toLocaleString()}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
