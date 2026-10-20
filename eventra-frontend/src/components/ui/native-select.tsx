import type { ComponentProps } from 'react'
import { cn } from '@/lib/utils'
import { controlClassName } from './input'

export function NativeSelect({
  className,
  children,
  ...props
}: ComponentProps<'select'>) {
  return (
    <select
      data-slot="native-select"
      className={cn(controlClassName, 'pr-8', className)}
      {...props}
    >
      {children}
    </select>
  )
}
