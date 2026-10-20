import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

type Tone = 'error' | 'success' | 'warning' | 'info'

const toneClass: Record<Tone, string> = {
  error: 'bg-danger-bg text-danger',
  success: 'bg-success-bg text-success',
  warning: 'bg-warning-bg text-warning',
  info: 'border border-border bg-card text-foreground',
}

// Inline message. Errors interrupt screen readers; the rest are polite.
export function Notice({
  tone = 'info',
  children,
  className,
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn(
        'rounded-md px-3.5 py-3 text-sm',
        toneClass[tone],
        className,
      )}
    >
      {children}
    </div>
  )
}
