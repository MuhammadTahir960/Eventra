import { HugeiconsIcon } from '@hugeicons/react'
import { Tick02Icon } from '@hugeicons/core-free-icons'
import { formatMoney } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { EventSeat } from '@/features/seating/types'
import { SwapLabel } from '@/components/SwapLabel'

export type PrinterStage = 'processing' | 'printing' | 'complete'

const STATUS: Record<PrinterStage, string> = {
  processing: 'Confirming your payment',
  printing: 'Printing your receipt',
  complete: 'Order complete',
}

// Torn paper edge: 40 teeth, 5px deep, as a clip-path polygon
const TEETH = 40
const TORN_EDGE = `polygon(0 0, 100% 0, ${Array.from(
  { length: TEETH + 1 },
  (_, i) => {
    const x = (i / TEETH) * 100
    return `${100 - x}% ${i % 2 === 0 ? '100%' : 'calc(100% - 5px)'}`
  },
).join(', ')})`

const stamp = new Intl.DateTimeFormat(undefined, {
  day: '2-digit',
  month: 'short',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

function Row({
  label,
  value,
  strong = false,
}: {
  label: string
  value: string
  strong?: boolean
}) {
  return (
    <div
      className={cn(
        'flex justify-between gap-4',
        strong && 'text-[15px] font-semibold',
      )}
    >
      <span className="min-w-0 wrap-anywhere">{label}</span>
      <span className="shrink-0">{value}</span>
    </div>
  )
}

// The checkout's last screen: a small printer that feeds the receipt out once
// the payment is confirmed. While Stripe's webhook is still on its way the
// screen says so and no paper shows.
export function ReceiptPrinter({
  stage,
  stalled = false,
  eventTitle,
  seats,
  total,
  orderId,
  paidAt,
  onPrinted,
}: {
  stage: PrinterStage
  // Still processing after the polling window ran out
  stalled?: boolean
  eventTitle: string | null
  seats: EventSeat[]
  total: string
  orderId: string
  paidAt: Date
  onPrinted: () => void
}) {
  const status = stalled ? 'Payment received, confirming' : STATUS[stage]

  return (
    <div className="mx-auto flex w-full max-w-[380px] flex-col items-center">
      {/* The machine */}
      <div className="relative z-10 w-full rounded-xl border border-hairline-strong bg-gradient-to-b from-card to-muted p-3 shadow-[0_1px_0_rgb(255_255_255/0.8)_inset,0_8px_20px_-12px_rgb(20_20_19/0.35)]">
        <div
          role="status"
          className="flex h-10 items-center gap-2.5 rounded-md bg-ink px-3 text-[13px] text-paper"
        >
          {stage === 'complete' ? (
            <HugeiconsIcon
              icon={Tick02Icon}
              size={16}
              className="text-[#7fd1a0]"
              aria-hidden
            />
          ) : (
            <span
              aria-hidden
              className={cn(
                'size-3.5 rounded-full border-2 border-paper/25 border-t-paper',
                !stalled && 'animate-spin',
              )}
            />
          )}
          <SwapLabel>{status}</SwapLabel>
        </div>
        {/* Paper slot */}
        <div className="mx-4 mt-3 h-1.5 rounded-full bg-ink/85 shadow-[0_1px_2px_rgb(0_0_0/0.4)_inset]" />
      </div>

      {/* The paper, clipped so it seems to come out of the slot */}
      <div className="-mt-2 w-[88%] overflow-hidden pb-4">
        <div
          onAnimationEnd={onPrinted}
          className={cn(
            'bg-card px-5 pt-6 pb-8 font-mono text-[12.5px] leading-relaxed text-ink drop-shadow-[0_6px_10px_rgb(20_20_19/0.12)]',
            stage === 'processing' && '-translate-y-full',
            stage === 'printing' && 'receipt-feed',
          )}
          style={{ clipPath: TORN_EDGE }}
          aria-hidden={stage === 'processing'}
        >
          <p className="text-center text-[13px] font-semibold tracking-[0.2em]">
            EVENTRA
          </p>
          <div className="my-3 border-t border-dashed border-hairline-strong" />
          {eventTitle && (
            <p className="font-semibold wrap-anywhere">{eventTitle}</p>
          )}
          <div className="mt-2 flex flex-col gap-1">
            {seats.map((seat) => (
              <Row
                key={seat.id}
                label={`${seat.section} ${seat.row_label}${seat.seat_number}`}
                value={formatMoney(seat.price)}
              />
            ))}
            <Row label="Booking fees" value={formatMoney(0)} />
          </div>
          <div className="my-3 border-t border-dashed border-hairline-strong" />
          <Row label="Total paid" value={formatMoney(total)} strong />
          <div className="mt-3 flex flex-col gap-0.5 text-muted-foreground">
            <Row label="Order" value={orderId.slice(0, 8).toUpperCase()} />
            <Row label="Paid" value={stamp.format(paidAt)} />
            <Row label="Card" value="Visa •••• 4242" />
          </div>
          <p className="mt-4 text-center text-muted-foreground">
            Your tickets are in My tickets.
          </p>
        </div>
      </div>
    </div>
  )
}
