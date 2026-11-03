import { cn } from '@/lib/utils'

// Placeholder while content loads; screen readers announce `label`
export function LoadingBlock({
  label,
  className,
}: {
  label: string
  className?: string
}) {
  return (
    <div
      aria-busy="true"
      aria-label={label}
      className={cn('animate-pulse rounded-lg bg-muted', className)}
    />
  )
}
