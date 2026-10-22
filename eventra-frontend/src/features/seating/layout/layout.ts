import {
  buildOutline,
  isClosedShape,
  offsetPointAt,
  type Outline,
  type VenueShape,
} from './shapes'

// ---------- tuning (SVG units; the map is scaled to fit the screen) ----------
export const SEAT_RADIUS = 5
const SEAT_PITCH = 14 // distance between seat centres along a row
const ROW_PITCH = 16 // distance between rows
const AISLE = SEAT_PITCH * 2 // gap between neighbouring sections
const LEVEL_GAP = 34 // gap between rings (100s, 200s, 300s levels)
const MIN_OUTLINE_LENGTH = 420
const FIELD_INSET = 14 // pitch/stage edge sits this far inside the first row
const BLOCK_PADDING = 2 // section background sticks out this far past its rows
const VIEW_PADDING = 28

// The minimum of what the layout needs from a seat
export interface LayoutSeatInput {
  id: string
  section: string
  row_label: string
  seat_number: number
}

export interface Bounds {
  minX: number
  minY: number
  maxX: number
  maxY: number
}

export interface SeatPosition {
  id: string
  x: number
  y: number
}

export interface SectionLayout {
  name: string
  // 0 for the innermost ring; 100s/200s/300s numbering gives several rings
  level: number
  // Background block behind the section's seats (an SVG path)
  path: string
  labelX: number
  labelY: number
  seatIds: string[]
  bounds: Bounds
}

export interface VenueLayout {
  shape: VenueShape
  seats: SeatPosition[]
  sections: SectionLayout[]
  // The pitch / stage / floor in the middle
  fieldPath: string
  fieldLabel: { x: number; y: number }
  viewBox: { x: number; y: number; width: number; height: number }
}

// "A2" before "A10", "101" before "1001"
const collator = new Intl.Collator(undefined, {
  numeric: true,
  sensitivity: 'base',
})
export const compareNatural = (a: string, b: string) => collator.compare(a, b)
const byName = compareNatural

interface SectionData {
  name: string
  rows: LayoutSeatInput[][]
  maxSeats: number
}

function groupSeats(seats: LayoutSeatInput[]): Map<string, SectionData> {
  const sections = new Map<string, Map<string, LayoutSeatInput[]>>()
  for (const seat of seats) {
    const rows = sections.get(seat.section) ?? new Map()
    const row = rows.get(seat.row_label) ?? []
    row.push(seat)
    rows.set(seat.row_label, row)
    sections.set(seat.section, rows)
  }

  const result = new Map<string, SectionData>()
  for (const name of [...sections.keys()].sort(byName)) {
    const rowMap = sections.get(name)!
    // Row A is closest to the stage, then B, C...
    const rows = [...rowMap.keys()]
      .sort(byName)
      .map((label) =>
        [...rowMap.get(label)!].sort((a, b) => a.seat_number - b.seat_number),
      )
    result.set(name, {
      name,
      rows,
      maxSeats: Math.max(...rows.map((row) => row.length)),
    })
  }
  return result
}

// Sections named 101-1xx, 201-2xx, 301-3xx sit on separate rings, like the
// lower / middle / upper bowls of a stadium. Anything else is a single ring.
function levelOf(names: string[]): Map<string, number> {
  const levels = new Map<string, number>()
  const allNumeric = names.every((name) => /^\d+$/.test(name))
  const hundreds = allNumeric
    ? [...new Set(names.map((name) => Math.floor(Number(name) / 100)))].sort(
        (a, b) => a - b,
      )
    : []

  for (const name of names) {
    levels.set(
      name,
      hundreds.length >= 2
        ? hundreds.indexOf(Math.floor(Number(name) / 100))
        : 0,
    )
  }
  return levels
}

const round = (value: number) => Math.round(value * 10) / 10

function pathFrom(points: { x: number; y: number }[]): string {
  return (
    points
      .map((p, i) => `${i === 0 ? 'M' : 'L'}${round(p.x)} ${round(p.y)}`)
      .join('') + 'Z'
  )
}

function emptyBounds(): Bounds {
  return { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity }
}

function extend(bounds: Bounds, x: number, y: number) {
  bounds.minX = Math.min(bounds.minX, x)
  bounds.minY = Math.min(bounds.minY, y)
  bounds.maxX = Math.max(bounds.maxX, x)
  bounds.maxY = Math.max(bounds.maxY, y)
}

// Lays every seat out around the venue's outline.
export function computeLayout(
  inputSeats: LayoutSeatInput[],
  shape: VenueShape,
): VenueLayout {
  const closed = isClosedShape(shape)
  const sectionData = groupSeats(inputSeats)
  const names = [...sectionData.keys()]
  const levelByName = levelOf(names)

  // Sections per ring, in order
  const rings: SectionData[][] = []
  for (const name of names) {
    const level = levelByName.get(name) ?? 0
    ;(rings[level] ??= []).push(sectionData.get(name)!)
  }

  // How far each ring starts from the stage edge
  const ringStart: number[] = []
  let cursor = 0
  rings.forEach((ring, index) => {
    ringStart[index] = cursor
    const depth = Math.max(...ring.map((s) => s.rows.length)) * ROW_PITCH
    cursor += depth + LEVEL_GAP
  })

  // Size the outline so the busiest ring still fits. Pushing a ring outward
  // by d lengthens its path by about (turning angle * d), which is why outer
  // rings can hold more seats than the outline itself is long.
  const turn = closed ? 2 * Math.PI : Math.PI
  let outlineLength = MIN_OUTLINE_LENGTH
  rings.forEach((ring, index) => {
    const gaps = closed ? ring.length : ring.length - 1
    const needed =
      ring.reduce((sum, s) => sum + s.maxSeats * SEAT_PITCH, 0) + gaps * AISLE
    const innerOffset = ringStart[index] + ROW_PITCH / 2
    outlineLength = Math.max(outlineLength, needed - turn * innerOffset)
  })
  const outline: Outline = buildOutline(shape, outlineLength)

  const bounds = emptyBounds()
  const seats: SeatPosition[] = []
  const sections: SectionLayout[] = []

  rings.forEach((ring, level) => {
    const gaps = closed ? ring.length : ring.length - 1
    const usable = outline.length - gaps * AISLE
    const totalWeight = ring.reduce((sum, s) => sum + s.maxSeats, 0)
    // Closed rings start half an aisle in so the gap is split across the seam
    let start = closed ? AISLE / 2 : 0

    for (const section of ring) {
      // Wider sections (more seats per row) get proportionally more length
      const length = (usable * section.maxSeats) / totalWeight
      const base = ringStart[level]
      const sectionBounds = emptyBounds()
      const seatIds: string[] = []

      section.rows.forEach((row, rowIndex) => {
        const offset = base + (rowIndex + 0.5) * ROW_PITCH
        row.forEach((seat, index) => {
          const s = start + (length * (index + 0.5)) / row.length
          const p = offsetPointAt(outline, s, offset)
          seats.push({ id: seat.id, x: round(p.x), y: round(p.y) })
          seatIds.push(seat.id)
          extend(sectionBounds, p.x, p.y)
          extend(bounds, p.x, p.y)
        })
      })

      // Background block: inner edge forwards, outer edge back
      const inner = base - BLOCK_PADDING
      const outer = base + section.rows.length * ROW_PITCH + BLOCK_PADDING
      const steps = Math.max(3, Math.ceil(length / 16))
      const edgeIn: { x: number; y: number }[] = []
      const edgeOut: { x: number; y: number }[] = []
      for (let i = 0; i <= steps; i += 1) {
        const s = start + (length * i) / steps
        edgeIn.push(offsetPointAt(outline, s, inner))
        edgeOut.push(offsetPointAt(outline, s, outer))
      }
      const block = [...edgeIn, ...edgeOut.reverse()]
      block.forEach((p) => {
        extend(sectionBounds, p.x, p.y)
        extend(bounds, p.x, p.y)
      })

      const label = offsetPointAt(outline, start + length / 2, outer + 11)
      extend(bounds, label.x, label.y)

      sections.push({
        name: section.name,
        level,
        path: pathFrom(block),
        labelX: round(label.x),
        labelY: round(label.y),
        seatIds,
        bounds: sectionBounds,
      })
      start += length + AISLE
    }
  })

  // Pitch / stage / floor, just inside the first row
  const field: { x: number; y: number }[] = []
  const fieldSteps = 120
  for (let i = 0; i <= fieldSteps; i += 1) {
    field.push(
      offsetPointAt(outline, (outline.length * i) / fieldSteps, -FIELD_INSET),
    )
  }
  field.forEach((p) => extend(bounds, p.x, p.y))
  const centre = field.reduce(
    (sum, p) => ({
      x: sum.x + p.x / field.length,
      y: sum.y + p.y / field.length,
    }),
    { x: 0, y: 0 },
  )

  return {
    shape,
    seats,
    sections,
    fieldPath: pathFrom(field),
    fieldLabel: { x: round(centre.x), y: round(centre.y) },
    viewBox: {
      x: round(bounds.minX - VIEW_PADDING),
      y: round(bounds.minY - VIEW_PADDING),
      width: round(bounds.maxX - bounds.minX + VIEW_PADDING * 2),
      height: round(bounds.maxY - bounds.minY + VIEW_PADDING * 2),
    },
  }
}
