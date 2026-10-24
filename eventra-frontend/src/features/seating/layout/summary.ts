import { compareNatural, type LayoutSeatInput } from './layout'

export interface SectionSummary {
  name: string
  rows: number
  seats: number
}

// Rows and seat totals per section, in natural order (S2 before S10)
export function summarizeSections(seats: LayoutSeatInput[]): SectionSummary[] {
  const bySection = new Map<string, { rows: Set<string>; seats: number }>()
  for (const seat of seats) {
    const entry = bySection.get(seat.section) ?? { rows: new Set(), seats: 0 }
    entry.rows.add(seat.row_label)
    entry.seats += 1
    bySection.set(seat.section, entry)
  }
  return [...bySection.entries()]
    .sort(([a], [b]) => compareNatural(a, b))
    .map(([name, entry]) => ({
      name,
      rows: entry.rows.size,
      seats: entry.seats,
    }))
}
