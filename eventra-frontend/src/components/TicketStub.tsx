import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

// The brand's one bold element: a ticket with a dashed tear line and side
// notches between its two halves. Used for the buy card, cart, order summary
// and tickets themselves.
export function TicketStub({
  children,
  stub,
  className,
  as: Tag = 'div',
  ...rest
}: {
  children: ReactNode
  // Content below the tear line (actions, totals)
  stub?: ReactNode
  className?: string
  as?: 'div' | 'section' | 'aside' | 'article'
} & Record<`aria-${string}`, string | undefined>) {
  return (
    <Tag
      className={cn(
        'relative overflow-hidden rounded-lg border border-border bg-card',
        className,
      )}
      {...rest}
    >
      <div className="p-5 sm:p-6">{children}</div>
      {stub && (
        <>
          <div
            aria-hidden
            className="relative border-t-[1.5px] border-dashed border-hairline-strong"
          >
            {/* Notches: page-coloured circles clipped by the card edge */}
            <span className="absolute -top-[11px] -left-[11px] size-5 rounded-full border border-border bg-background" />
            <span className="absolute -top-[11px] -right-[11px] size-5 rounded-full border border-border bg-background" />
          </div>
          <div className="p-5 sm:p-6">{stub}</div>
        </>
      )}
    </Tag>
  )
}
