import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

// An empty list is an invitation to act: say what's missing and what to do
export function EmptyState({
  title,
  body,
  action,
  className,
}: {
  title: string
  body?: ReactNode
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center gap-2 rounded-lg border border-dashed border-hairline-strong px-6 py-14 text-center',
        className,
      )}
    >
      <p className="font-display text-[28px] leading-tight">{title}</p>
      {body && (
        <p className="max-w-md text-[15px] text-muted-foreground">{body}</p>
      )}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}
