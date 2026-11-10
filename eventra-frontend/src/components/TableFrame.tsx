import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

// Bordered frame that scrolls a wide `.data-table` sideways; `dimmed` while
// the next page loads
export function TableFrame({
  dimmed = false,
  children,
}: {
  dimmed?: boolean
  children: ReactNode
}) {
  return (
    <div
      className={cn(
        'relative overflow-x-auto rounded-lg border border-border bg-card',
        dimmed && 'opacity-60',
      )}
    >
      <table className="data-table">{children}</table>
    </div>
  )
}
