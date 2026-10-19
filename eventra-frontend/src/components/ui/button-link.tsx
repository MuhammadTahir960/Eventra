import type { VariantProps } from 'class-variance-authority'
import { Link, type LinkProps } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { buttonVariants } from './button'

export function ButtonLink({
  variant,
  size,
  className,
  ...props
}: LinkProps & VariantProps<typeof buttonVariants>) {
  return (
    <Link
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}
