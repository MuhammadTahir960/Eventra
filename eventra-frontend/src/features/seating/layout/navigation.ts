import { compareNatural, type LayoutSeatInput } from './layout'

// Keyboard navigation for the seat map. Only one seat is in the tab order
// (a "roving" tab stop); arrow keys then move between neighbours, so a
// 1,000-seat venue costs one Tab press instead of a thousand.

interface Place {
  section: string
  row: number
  column: number
}

export interface SeatNavigation {
  // section -> rows (nearest the stage first) -> seat ids in seat-number order
  rows: Map<string, string[][]>
  places: Map<string, Place>
  // The first seat in reading order: where the tab stop starts
  first: string | null
}

export function buildNavigation(seats: LayoutSeatInput[]): SeatNavigation {
  const grouped = new Map<string, Map<string, LayoutSeatInput[]>>()
  for (const seat of seats) {
    const rows = grouped.get(seat.section) ?? new Map()
    const row = rows.get(seat.row_label) ?? []
    row.push(seat)
    rows.set(seat.row_label, row)
    grouped.set(seat.section, rows)
  }

  const rows = new Map<string, string[][]>()
  const places = new Map<string, Place>()
  let first: string | null = null

  for (const section of [...grouped.keys()].sort(compareNatural)) {
    const rowMap = grouped.get(section)!
    const ordered = [...rowMap.keys()]
      .sort(compareNatural)
      .map((label) =>
        [...rowMap.get(label)!]
          .sort((a, b) => a.seat_number - b.seat_number)
          .map((seat) => seat.id),
      )
    rows.set(section, ordered)
    ordered.forEach((ids, rowIndex) =>
      ids.forEach((id, column) => {
        places.set(id, { section, row: rowIndex, column })
        first ??= id
      }),
    )
  }
  return { rows, places, first }
}

export type NavigationKey =
  'ArrowLeft' | 'ArrowRight' | 'ArrowUp' | 'ArrowDown' | 'Home' | 'End'

export function isNavigationKey(key: string): key is NavigationKey {
  return [
    'ArrowLeft',
    'ArrowRight',
    'ArrowUp',
    'ArrowDown',
    'Home',
    'End',
  ].includes(key)
}

// Left/Right: along the row. Up/Down: to the next row of the same section,
// keeping roughly the same position. Home/End: row ends. Edges stay put.
export function moveFocus(
  nav: SeatNavigation,
  id: string,
  key: NavigationKey,
): string {
  const place = nav.places.get(id)
  if (!place) return id
  const rows = nav.rows.get(place.section)!
  const row = rows[place.row]

  switch (key) {
    case 'ArrowLeft':
      return row[Math.max(place.column - 1, 0)]
    case 'ArrowRight':
      return row[Math.min(place.column + 1, row.length - 1)]
    case 'Home':
      return row[0]
    case 'End':
      return row[row.length - 1]
    case 'ArrowUp':
    case 'ArrowDown': {
      const target = place.row + (key === 'ArrowUp' ? -1 : 1)
      if (target < 0 || target >= rows.length) return id
      const next = rows[target]
      // Same relative position along the new row (rows can differ in length)
      const ratio = row.length > 1 ? place.column / (row.length - 1) : 0
      return next[Math.round(ratio * (next.length - 1))]
    }
  }
}
