import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'

export const controlClassName =
  'h-11 w-full rounded-md border border-input bg-card px-3 text-[15px] outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/20 aria-invalid:border-destructive aria-invalid:ring-2 aria-invalid:ring-destructive/15 disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60'

export function Input({
  className,
  type = 'text',
  ...props
}: ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(controlClassName, className)}
      {...props}
    />
  )
}
