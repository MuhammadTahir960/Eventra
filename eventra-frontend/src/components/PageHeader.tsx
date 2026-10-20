import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

// Serif page title with optional supporting line and actions on the right
export function PageHeader({
  title,
  description,
  actions,
  size = 'lg',
  className,
}: {
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
  // 'md' for workspace pages, which sit in a denser layout
  size?: 'lg' | 'md'
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between',
        className,
      )}
    >
      <div className="flex min-w-0 flex-col gap-1.5">
        <h1
          className={cn(
            'font-display leading-[1.05]',
            size === 'lg'
              ? 'text-[clamp(2.5rem,6vw,3.75rem)]'
              : 'text-[clamp(2rem,4vw,2.5rem)]',
          )}
        >
          {title}
        </h1>
        {description && (
          <p className="tabular text-[15px] text-muted-foreground">
            {description}
          </p>
        )}
      </div>
      {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
    </div>
  )
}
