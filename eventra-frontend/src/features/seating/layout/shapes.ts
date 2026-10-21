// Venue outlines for the bird's-eye seat map.
//
// An outline is the line the first row of seats follows around the stage or
// pitch. Every point also carries an "outward normal" (the direction away
// from the stage), so a row N steps back is just the outline pushed outward.
// Sections are then placed along the outline, which is what makes a round
// venue look round and a U-shaped venue look like a U.

export const VENUE_SHAPES = [
  'oval',
  'circle',
  'rectangle',
  'u_shape',
  'semicircle',
] as const

export type VenueShape = (typeof VENUE_SHAPES)[number]

export function isVenueShape(value: unknown): value is VenueShape {
  return (
    typeof value === 'string' &&
    (VENUE_SHAPES as readonly string[]).includes(value)
  )
}

// Seating wraps all the way around these; the others have an open side
export function isClosedShape(shape: VenueShape): boolean {
  return shape !== 'u_shape' && shape !== 'semicircle'
}

export interface OutlinePoint {
  x: number
  y: number
  // Unit vector pointing away from the stage
  nx: number
  ny: number
}

export interface Outline {
  closed: boolean
  length: number
  points: OutlinePoint[]
  // cum[i] is the distance along the outline to points[i]
  cum: number[]
}

// ---------- building blocks for the raw (unscaled) shapes ----------

const STEPS_PER_UNIT = 48

function normalise(nx: number, ny: number): [number, number] {
  const size = Math.hypot(nx, ny) || 1
  return [nx / size, ny / size]
}

function addLine(
  out: OutlinePoint[],
  from: [number, number],
  to: [number, number],
  normal: [number, number],
) {
  const steps = Math.max(
    2,
    Math.ceil(Math.hypot(to[0] - from[0], to[1] - from[1]) * STEPS_PER_UNIT),
  )
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps
    out.push({
      x: from[0] + (to[0] - from[0]) * t,
      y: from[1] + (to[1] - from[1]) * t,
      nx: normal[0],
      ny: normal[1],
    })
  }
}

// Arc of an ellipse; the normal is the ellipse's own outward normal
function addArc(
  out: OutlinePoint[],
  center: [number, number],
  rx: number,
  ry: number,
  from: number,
  to: number,
) {
  const length = Math.abs(to - from) * Math.max(rx, ry)
  const steps = Math.max(8, Math.ceil(length * STEPS_PER_UNIT))
  for (let i = 0; i <= steps; i += 1) {
    const angle = from + ((to - from) * i) / steps
    const [nx, ny] = normalise(Math.cos(angle) / rx, Math.sin(angle) / ry)
    out.push({
      x: center[0] + rx * Math.cos(angle),
      y: center[1] + ry * Math.sin(angle),
      nx,
      ny,
    })
  }
}

// y grows downward (SVG), so increasing angles run clockwise on screen
const TOP = -Math.PI / 2

function rawPoints(shape: VenueShape): OutlinePoint[] {
  const out: OutlinePoint[] = []
  switch (shape) {
    case 'circle':
      addArc(out, [0, 0], 1, 1, TOP, TOP + 2 * Math.PI)
      break
    case 'oval':
      addArc(out, [0, 0], 1.8, 1, TOP, TOP + 2 * Math.PI)
      break
    case 'rectangle': {
      // Rounded rectangle, clockwise from the top-left of the top edge
      const w = 1.7
      const h = 1
      const r = 0.45
      addLine(out, [-w + r, -h], [w - r, -h], [0, -1])
      addArc(out, [w - r, -h + r], r, r, TOP, 0)
      addLine(out, [w, -h + r], [w, h - r], [1, 0])
      addArc(out, [w - r, h - r], r, r, 0, Math.PI / 2)
      addLine(out, [w - r, h], [-w + r, h], [0, 1])
      addArc(out, [-w + r, h - r], r, r, Math.PI / 2, Math.PI)
      addLine(out, [-w, h - r], [-w, -h + r], [-1, 0])
      addArc(out, [-w + r, -h + r], r, r, Math.PI, Math.PI * 1.5)
      break
    }
    case 'u_shape': {
      // Down the left arm, around a rounded bottom, up the right arm.
      // The open side is the top, where the stage sits.
      const a = 1.2
      const arm = 1.5
      addLine(out, [-a, -arm], [-a, 0], [-1, 0])
      addArc(out, [0, 0], a, a, Math.PI, 0)
      addLine(out, [a, 0], [a, -arm], [1, 0])
      break
    }
    case 'semicircle':
      // Half an oval wrapped around the stage, open at the top
      addArc(out, [0, 0], 1.8, 1, Math.PI, 0)
      break
  }
  return out
}

// Drop repeated points, add cumulative distances, and close loops
function finish(points: OutlinePoint[], closed: boolean): Outline {
  const unique: OutlinePoint[] = []
  for (const point of points) {
    const last = unique.at(-1)
    if (!last || Math.hypot(point.x - last.x, point.y - last.y) > 1e-9) {
      unique.push(point)
    }
  }
  const first = unique[0]
  const last = unique.at(-1)
  if (
    closed &&
    first &&
    last &&
    Math.hypot(first.x - last.x, first.y - last.y) > 1e-9
  ) {
    unique.push({ ...first })
  }

  const cum = [0]
  for (let i = 1; i < unique.length; i += 1) {
    const a = unique[i - 1]
    const b = unique[i]
    cum.push(cum[i - 1] + Math.hypot(b.x - a.x, b.y - a.y))
  }
  return { closed, length: cum.at(-1) ?? 0, points: unique, cum }
}

// The shape scaled so its total length is exactly `length`.
// Bigger venues get a bigger outline; seat sizes never change.
export function buildOutline(shape: VenueShape, length: number): Outline {
  const raw = finish(rawPoints(shape), isClosedShape(shape))
  const k = length / raw.length
  return {
    closed: raw.closed,
    length,
    points: raw.points.map((p) => ({ ...p, x: p.x * k, y: p.y * k })),
    cum: raw.cum.map((c) => c * k),
  }
}

// Position and outward normal at distance `s` along the outline
export function pointAt(outline: Outline, s: number): OutlinePoint {
  const { points, cum, length, closed } = outline
  // Closed outlines wrap around; open ones stop at their ends
  const at = closed
    ? ((s % length) + length) % length
    : Math.min(Math.max(s, 0), length)

  // Binary search for the segment containing `at`
  let low = 0
  let high = cum.length - 1
  while (high - low > 1) {
    const mid = (low + high) >> 1
    if (cum[mid] <= at) low = mid
    else high = mid
  }

  const a = points[low]
  const b = points[high]
  const span = cum[high] - cum[low]
  const t = span > 0 ? (at - cum[low]) / span : 0
  const [nx, ny] = normalise(a.nx + (b.nx - a.nx) * t, a.ny + (b.ny - a.ny) * t)
  return { x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t, nx, ny }
}

// A point `distance` away from the outline, pushed outward from the stage
export function offsetPointAt(
  outline: Outline,
  s: number,
  distance: number,
): { x: number; y: number } {
  const p = pointAt(outline, s)
  return { x: p.x + p.nx * distance, y: p.y + p.ny * distance }
}
