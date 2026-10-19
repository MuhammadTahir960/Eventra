import { useId } from 'react'
import { cn } from '@/lib/utils'

// The ticket-notch "e": a ticket with side notches, and the e's crossbar
// running between them like a tear line.
export function LogoMark({
  size = 28,
  mono = false,
  className,
}: {
  size?: number
  mono?: boolean
  className?: string
}) {
  // Each instance needs its own mask id or they'd collide on the page
  const maskId = useId()
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      aria-hidden
      className={cn('shrink-0', className)}
    >
      <mask
        id={maskId}
        maskUnits="userSpaceOnUse"
        x="0"
        y="0"
        width="32"
        height="32"
      >
        <rect width="32" height="32" fill="#fff" />
        <circle cx="0" cy="16" r="3.4" fill="#000" />
        <circle cx="32" cy="16" r="3.4" fill="#000" />
      </mask>
      <rect
        width="32"
        height="32"
        rx="8"
        fill={mono ? 'var(--ink)' : 'var(--ember)'}
        mask={`url(#${maskId})`}
      />
      <path
        d="M8.6 16 H23.2 A7.2 7.2 0 1 0 21.4 20.8"
        fill="none"
        stroke="#fff"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function Logo({
  size = 28,
  inverted = false,
  className,
}: {
  size?: number
  inverted?: boolean
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <LogoMark size={size} />
      <span
        className={cn(
          'font-semibold tracking-[-0.035em]',
          inverted ? 'text-paper' : 'text-ink',
        )}
        style={{ fontSize: size * 0.78 }}
      >
        eventra
      </span>
    </span>
  )
}
