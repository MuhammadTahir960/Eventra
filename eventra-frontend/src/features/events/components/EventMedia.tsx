import { ImageWithFallback } from '@/components/ImageWithFallback'
import { initial } from '@/lib/initial'
import { cn } from '@/lib/utils'
import type { EventItem } from '../types'
import type { EventRefs } from '../lookups'

// An event's picture. Events have no image of their own, so in order:
// the venue photo, the two team logos for a match, or a serif initial.
export function EventMedia({
  event,
  refs,
  className,
  eager = false,
}: {
  event: EventItem
  refs: EventRefs
  className?: string
  eager?: boolean
}) {
  const { venue, home, away } = refs
  const base = cn('relative overflow-hidden rounded-lg', className)

  if (event.event_type === 'sports_match' && home && away) {
    return (
      <div
        className={cn(
          base,
          'grid place-items-center border border-border bg-card',
        )}
      >
        <div className="flex items-center gap-[8%] px-[8%]">
          <TeamBadge name={home.name} logo={home.logo} />
          <span className="font-display text-2xl text-muted-foreground">v</span>
          <TeamBadge name={away.name} logo={away.logo} />
        </div>
      </div>
    )
  }

  const monogram = (
    <div
      className={cn(
        base,
        'grid place-items-center border border-border bg-muted',
      )}
    >
      <span
        aria-hidden
        className="font-display text-[clamp(4rem,9vw,7.5rem)] leading-none"
      >
        {initial(event.title)}
        <span className="text-ember">.</span>
      </span>
    </div>
  )

  if (!venue?.photo) return monogram

  return (
    <ImageWithFallback
      src={venue.photo}
      alt=""
      loading={eager ? 'eager' : 'lazy'}
      // A missing upload falls back to the monogram, not a broken icon
      fallback={monogram}
      className={cn(base, 'bg-muted object-cover')}
    />
  )
}

function TeamBadge({ name, logo }: { name: string; logo: string | null }) {
  const letter = (
    <span
      aria-hidden
      className="grid aspect-square w-[min(28%,6rem)] min-w-12 place-items-center rounded-full bg-muted font-display text-3xl"
    >
      {initial(name)}
    </span>
  )
  return logo ? (
    <ImageWithFallback
      src={logo}
      alt=""
      loading="lazy"
      fallback={letter}
      className="aspect-square w-[min(28%,6rem)] min-w-12 object-contain"
    />
  ) : (
    letter
  )
}
