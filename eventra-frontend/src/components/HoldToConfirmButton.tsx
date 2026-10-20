import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type PointerEvent,
} from 'react'
import { cn } from '@/lib/utils'
import { SwapLabel } from './SwapLabel'

type Phase = 'idle' | 'holding' | 'confirmed'

const ROLLBACK_MS = 180

// For the most destructive actions: press and hold (pointer, Enter or Space)
// until the fill reaches the end. Releasing early rolls the fill back, so a
// stray click can never fire it.
export function HoldToConfirmButton({
  label,
  confirmedLabel,
  onConfirm,
  durationMs = 1600,
  disabled = false,
  hintId,
}: {
  label: string
  // Shown once the hold completes, while the action runs
  confirmedLabel: string
  onConfirm: () => void
  durationMs?: number
  disabled?: boolean
  // id of visible text that explains the hold, for aria-describedby
  hintId?: string
}) {
  const [phase, setPhase] = useState<Phase>('idle')
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  // To re-arm after a failed request, the parent remounts it with a new key
  useEffect(() => () => clearTimeout(timer.current), [])

  function start() {
    if (disabled || phase !== 'idle') return
    setPhase('holding')
    timer.current = setTimeout(() => {
      setPhase('confirmed')
      onConfirm()
    }, durationMs)
  }

  function cancel() {
    if (phase !== 'holding') return
    clearTimeout(timer.current)
    setPhase('idle')
  }

  function onPointerDown(event: PointerEvent<HTMLButtonElement>) {
    if (event.button !== 0) return
    // Keep receiving pointer events even if the finger drifts off the button
    event.currentTarget.setPointerCapture?.(event.pointerId)
    start()
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>) {
    if ((event.key === 'Enter' || event.key === ' ') && !event.repeat) {
      event.preventDefault()
      start()
    }
  }

  function onKeyUp(event: KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'Enter' || event.key === ' ') cancel()
  }

  const filled = phase !== 'idle'
  const text = phase === 'confirmed' ? confirmedLabel : label

  return (
    <button
      type="button"
      disabled={disabled && phase !== 'confirmed'}
      aria-busy={phase === 'holding' || undefined}
      aria-describedby={hintId}
      onPointerDown={onPointerDown}
      onPointerUp={cancel}
      onPointerCancel={cancel}
      onLostPointerCapture={cancel}
      onKeyDown={onKeyDown}
      onKeyUp={onKeyUp}
      onBlur={cancel}
      // No context menu or text selection from a long press on touch screens
      onContextMenu={(event) => event.preventDefault()}
      className="relative inline-flex h-10 touch-none items-center justify-center overflow-hidden rounded-md border border-danger-line bg-card px-4 text-sm font-medium text-danger transition-[scale] duration-160 ease-out select-none active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:active:scale-100"
    >
      <SwapLabel>{text}</SwapLabel>
      {/* The fill: same label in white on solid danger, revealed left to right */}
      <span
        aria-hidden
        className={cn(
          'absolute inset-0 flex items-center justify-center bg-danger text-white',
          phase === 'idle' ? 'ease-out' : 'ease-linear',
        )}
        style={{
          clipPath: filled ? 'inset(0 0 0 0)' : 'inset(0 100% 0 0)',
          transitionProperty: 'clip-path',
          transitionDuration: `${phase === 'holding' ? durationMs : phase === 'idle' ? ROLLBACK_MS : 0}ms`,
        }}
      >
        <SwapLabel>{text}</SwapLabel>
      </span>
    </button>
  )
}
