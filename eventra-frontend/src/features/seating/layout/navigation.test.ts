import { describe, expect, it } from 'vitest'
import type { LayoutSeatInput } from './layout'
import { buildNavigation, isNavigationKey, moveFocus } from './navigation'

// Section A has rows A (3 seats) and B (5 seats); section B has one row
const seat = (
  section: string,
  row_label: string,
  seat_number: number,
): LayoutSeatInput => ({
  id: `${section}${row_label}${seat_number}`,
  section,
  row_label,
  seat_number,
})

const SEATS: LayoutSeatInput[] = [
  // Deliberately out of order to prove sorting
  seat('A', 'A', 3),
  seat('A', 'A', 1),
  seat('A', 'A', 2),
  ...[1, 2, 3, 4, 5].map((n) => seat('A', 'B', n)),
  seat('B', 'A', 1),
]

const nav = buildNavigation(SEATS)

describe('buildNavigation', () => {
  it('starts at the first seat in reading order', () => {
    expect(nav.first).toBe('AA1')
  })

  it('knows every seat', () => {
    expect(nav.places.size).toBe(SEATS.length)
  })

  it('has no starting seat for an empty venue', () => {
    expect(buildNavigation([]).first).toBeNull()
  })
})

describe('moveFocus', () => {
  it('moves along a row', () => {
    expect(moveFocus(nav, 'AA2', 'ArrowRight')).toBe('AA3')
    expect(moveFocus(nav, 'AA2', 'ArrowLeft')).toBe('AA1')
  })

  it('stops at the ends of a row', () => {
    expect(moveFocus(nav, 'AA1', 'ArrowLeft')).toBe('AA1')
    expect(moveFocus(nav, 'AA3', 'ArrowRight')).toBe('AA3')
  })

  it('jumps to row ends with Home and End', () => {
    expect(moveFocus(nav, 'AB3', 'Home')).toBe('AB1')
    expect(moveFocus(nav, 'AB3', 'End')).toBe('AB5')
  })

  it('moves between rows keeping the relative position', () => {
    // Middle of a 3-seat row -> middle of the 5-seat row
    expect(moveFocus(nav, 'AA2', 'ArrowDown')).toBe('AB3')
    // First seat stays first, last stays last
    expect(moveFocus(nav, 'AA1', 'ArrowDown')).toBe('AB1')
    expect(moveFocus(nav, 'AA3', 'ArrowDown')).toBe('AB5')
    expect(moveFocus(nav, 'AB5', 'ArrowUp')).toBe('AA3')
  })

  it('stays put at the first and last row of a section', () => {
    expect(moveFocus(nav, 'AA2', 'ArrowUp')).toBe('AA2')
    expect(moveFocus(nav, 'AB2', 'ArrowDown')).toBe('AB2')
  })

  it('never crosses into another section', () => {
    expect(moveFocus(nav, 'AB5', 'ArrowDown')).toBe('AB5')
    expect(moveFocus(nav, 'BA1', 'ArrowRight')).toBe('BA1')
  })

  it('ignores a seat it does not know', () => {
    expect(moveFocus(nav, 'missing', 'ArrowRight')).toBe('missing')
  })
})

describe('isNavigationKey', () => {
  it('recognises navigation keys only', () => {
    expect(isNavigationKey('ArrowUp')).toBe(true)
    expect(isNavigationKey('Home')).toBe(true)
    expect(isNavigationKey('Enter')).toBe(false)
    expect(isNavigationKey('a')).toBe(false)
  })
})
