import { describe, expect, it } from 'vitest'
import type { LayoutSeatInput } from './layout'
import { summarizeSections } from './summary'

const seat = (
  section: string,
  row_label: string,
  seat_number: number,
): LayoutSeatInput => ({
  id: `${section}-${row_label}-${seat_number}`,
  section,
  row_label,
  seat_number,
})

describe('summarizeSections', () => {
  it('counts rows and seats per section', () => {
    const summary = summarizeSections([
      seat('VIP', 'A', 1),
      seat('VIP', 'A', 2),
      seat('VIP', 'B', 1),
      seat('Economy', 'A', 1),
    ])
    expect(summary).toEqual([
      { name: 'Economy', rows: 1, seats: 1 },
      { name: 'VIP', rows: 2, seats: 3 },
    ])
  })

  it('orders sections naturally (S2 before S10)', () => {
    const summary = summarizeSections([seat('S10', 'A', 1), seat('S2', 'A', 1)])
    expect(summary.map((s) => s.name)).toEqual(['S2', 'S10'])
  })

  it('returns nothing for an empty venue', () => {
    expect(summarizeSections([])).toEqual([])
  })
})
