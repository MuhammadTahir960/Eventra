import type { ReactNode } from 'react'

// A button label that eases in when it changes ("Pay" -> "Processing…"),
// instead of jumping. The key remounts the span, and @starting-style plays
// the entrance; the old label leaves instantly. Reduced motion keeps the
// fade and drops the 8px rise.
export function SwapLabel({
  children,
  swapKey,
}: {
  children: ReactNode
  // Identity of the state; defaults to the text itself
  swapKey?: string
}) {
  return (
    <span
      key={swapKey ?? String(children)}
      className="inline-flex items-center gap-2 transition-[opacity,translate] duration-180 ease-out starting:translate-y-2 starting:opacity-0 motion-reduce:starting:translate-y-0"
    >
      {children}
    </span>
  )
}
