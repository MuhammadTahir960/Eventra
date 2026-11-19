import { formatMoney } from '@/lib/format'

export function TotalRow({
  total,
  currency,
}: {
  total: string | number
  currency: string | null | undefined
}) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="font-medium">Total</span>
      <span className="tabular text-xl font-semibold">
        {formatMoney(total, currency)}
      </span>
    </div>
  )
}
