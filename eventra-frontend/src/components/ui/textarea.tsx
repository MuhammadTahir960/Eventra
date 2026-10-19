import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
import { controlClassName } from './input'

export function Textarea({ className, ...props }: ComponentProps<'textarea'>) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(controlClassName, 'h-auto min-h-24 py-2', className)}
      {...props}
    />
  )
}
