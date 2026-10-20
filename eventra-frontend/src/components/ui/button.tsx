import { Button as ButtonPrimitive } from '@base-ui/react/button'
import { cva, type VariantProps } from 'class-variance-authority'

import { cn } from '@/lib/utils'

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-md border border-transparent font-medium whitespace-nowrap transition-[background-color,border-color,color,scale] duration-160 ease-out select-none active:not-disabled:scale-[0.97] motion-reduce:active:not-disabled:scale-100 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: 'bg-ember-deep text-white hover:bg-ember-deeper',
        ink: 'bg-ink text-paper hover:bg-ink/85',
        outline:
          'border-hairline-strong bg-card text-foreground hover:bg-muted aria-expanded:bg-muted',
        ghost: 'text-foreground hover:bg-muted aria-expanded:bg-muted',
        destructive:
          'border-danger-line bg-card text-danger hover:bg-danger-bg',
        link: 'text-ember-deep underline-offset-4 hover:underline',
      },
      size: {
        default: 'h-10 px-4 text-sm',
        sm: 'h-8 px-3 text-[13px]',
        lg: 'h-12 px-5 text-[15px]',
        icon: 'size-10',
        'icon-sm': 'size-8',
      },
    },
    defaultVariants: {
      variant: 'default',
      size: 'default',
    },
  },
)

function Button({
  className,
  variant = 'default',
  size = 'default',
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
