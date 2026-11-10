import { formatMoney } from '@/lib/format'

export function TotalRow({ total }: { total: string | number }) {
  return (
    <div className="flex items-baseline justify-between">
      <span className="font-medium">Total</span>
      <span className="tabular text-xl font-semibold">
        {formatMoney(total)}
      </span>
    </div>
  )
}
