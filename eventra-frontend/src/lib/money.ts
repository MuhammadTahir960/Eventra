// Prices arrive as decimal strings ("45.00"). Adding them as JavaScript
// numbers can drift (0.1 + 0.2), so totals are summed as whole cents.

// Most endpoints send decimal strings, but the seat map sends JSON numbers
// (45.0), so both are accepted. A number is rounded to whole cents.
export type Price = string | number

export function toCents(price: Price): number {
  if (typeof price === 'number') {
    return Number.isFinite(price) && price >= 0
      ? Math.round(price * 100)
      : Number.NaN
  }
  const match = /^(\d+)(?:\.(\d{1,2}))?$/.exec(price.trim())
  if (!match) return Number.NaN
  const dollars = Number(match[1])
  const cents = Number((match[2] ?? '').padEnd(2, '0'))
  return dollars * 100 + cents
}

// Sum of prices, as a decimal string with two places
export function sumPrices(prices: Price[]): string {
  const total = prices.reduce<number>((sum, price) => sum + toCents(price), 0)
  if (!Number.isFinite(total)) return '0.00'
  const dollars = Math.floor(total / 100)
  const cents = String(total % 100).padStart(2, '0')
  return `${dollars}.${cents}`
}
