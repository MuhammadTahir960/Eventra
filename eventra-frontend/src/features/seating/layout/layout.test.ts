import { describe, expect, it } from 'vitest'
import { computeLayout, SEAT_RADIUS, type LayoutSeatInput } from './layout'
import { VENUE_SHAPES, type VenueShape } from './shapes'

interface SectionSpec {
  name: string
  rows: number
  seatsPerRow: number
}

// Builds seats the way the backend labels them: section, row letter, number
function makeSeats(sections: SectionSpec[]): LayoutSeatInput[] {
  const seats: LayoutSeatInput[] = []
  for (const section of sections) {
    for (let r = 0; r < section.rows; r += 1) {
      for (let n = 1; n <= section.seatsPerRow; n += 1) {
        seats.push({
          id: `${section.name}-${r}-${n}`,
          section: section.name,
          row_label: String.fromCharCode(65 + r),
          seat_number: n,
        })
      }
    }
  }
  return seats
}

const SMALL: SectionSpec[] = ['A', 'B', 'C', 'D', 'E', 'F'].map((name) => ({
  name,
  rows: 5,
  seatsPerRow: 10,
}))

// Smallest distance between any two seat centres
function minDistance(points: { x: number; y: number }[]): number {
  let min = Infinity
  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      min = Math.min(
        min,
        Math.hypot(points[i].x - points[j].x, points[i].y - points[j].y),
      )
    }
  }
  return min
}

describe('computeLayout', () => {
  it.each(VENUE_SHAPES)(
    'places every seat exactly once on a %s venue',
    (shape) => {
      const seats = makeSeats(SMALL)
      const layout = computeLayout(seats, shape)

      expect(layout.seats).toHaveLength(seats.length)
      expect(new Set(layout.seats.map((s) => s.id)).size).toBe(seats.length)
      for (const seat of layout.seats) {
        expect(Number.isFinite(seat.x)).toBe(true)
        expect(Number.isFinite(seat.y)).toBe(true)
      }
    },
  )

  it.each(VENUE_SHAPES)('never lets seats overlap on a %s venue', (shape) => {
    const layout = computeLayout(makeSeats(SMALL), shape)
    // Seat circles must not touch (radius * 2 apart, with a little slack)
    expect(minDistance(layout.seats)).toBeGreaterThan(SEAT_RADIUS * 1.8)
  })

  it('keeps seats from overlapping in a large venue too', () => {
    const big = Array.from({ length: 8 }, (_, i) => ({
      name: String(i + 1),
      rows: 10,
      seatsPerRow: 20,
    }))
    const layout = computeLayout(makeSeats(big), 'oval')
    expect(layout.seats).toHaveLength(1600)
    expect(minDistance(layout.seats)).toBeGreaterThan(SEAT_RADIUS * 1.8)
  })

  it('draws a circular venue round and an oval venue wide', () => {
    const ratio = (shape: VenueShape) => {
      const { width, height } = computeLayout(makeSeats(SMALL), shape).viewBox
      return width / height
    }
    expect(ratio('circle')).toBeGreaterThan(0.95)
    expect(ratio('circle')).toBeLessThan(1.05)
    expect(ratio('oval')).toBeGreaterThan(1.4)
    expect(ratio('rectangle')).toBeGreaterThan(1.3)
  })

  it('leaves the open side of a U-shaped venue empty', () => {
    const layout = computeLayout(makeSeats(SMALL), 'u_shape')
    const { x, y, width, height } = layout.viewBox
    const centreX = x + width / 2
    const middleY = y + height / 2
    // Along the centre line, seats exist only in the curved bottom,
    // never up in the open mouth of the U. (The tolerance is wide because
    // an aisle between sections falls right at the bottom centre.)
    const onCentreLine = layout.seats.filter(
      (seat) => Math.abs(seat.x - centreX) < 40,
    )
    expect(onCentreLine.length).toBeGreaterThan(0)
    expect(onCentreLine.every((seat) => seat.y > middleY)).toBe(true)
  })

  it('puts numbered 100s/200s sections on separate rings', () => {
    const sections = [
      '101',
      '102',
      '103',
      '104',
      '201',
      '202',
      '203',
      '204',
    ].map((name) => ({ name, rows: 4, seatsPerRow: 10 }))
    const layout = computeLayout(makeSeats(sections), 'circle')

    const centre = {
      x: layout.viewBox.x + layout.viewBox.width / 2,
      y: layout.viewBox.y + layout.viewBox.height / 2,
    }
    const distance = (id: string) => {
      const seat = layout.seats.find((s) => s.id === id)!
      return Math.hypot(seat.x - centre.x, seat.y - centre.y)
    }
    expect(layout.sections.filter((s) => s.level === 0)).toHaveLength(4)
    expect(layout.sections.filter((s) => s.level === 1)).toHaveLength(4)
    // Every seat of the 200s ring is farther out than every seat in the 100s
    expect(distance('201-0-5')).toBeGreaterThan(distance('101-3-5'))
  })

  it('treats names that are not numbered by hundreds as one ring', () => {
    const layout = computeLayout(makeSeats(SMALL), 'oval')
    expect(new Set(layout.sections.map((s) => s.level))).toEqual(new Set([0]))
  })

  it('orders sections and rows naturally (A2 before A10, row A nearest the stage)', () => {
    const layout = computeLayout(
      makeSeats([
        { name: 'S10', rows: 2, seatsPerRow: 5 },
        { name: 'S2', rows: 2, seatsPerRow: 5 },
      ]),
      'circle',
    )
    expect(layout.sections.map((s) => s.name)).toEqual(['S2', 'S10'])

    const centre = {
      x: layout.viewBox.x + layout.viewBox.width / 2,
      y: layout.viewBox.y + layout.viewBox.height / 2,
    }
    const distance = (id: string) => {
      const seat = layout.seats.find((s) => s.id === id)!
      return Math.hypot(seat.x - centre.x, seat.y - centre.y)
    }
    expect(distance('S2-0-3')).toBeLessThan(distance('S2-1-3'))
  })

  it('handles a venue with no seats without crashing', () => {
    const layout = computeLayout([], 'oval')
    expect(layout.seats).toEqual([])
    expect(layout.sections).toEqual([])
  })
})
