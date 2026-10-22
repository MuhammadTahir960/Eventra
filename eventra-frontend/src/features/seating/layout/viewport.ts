import type { Bounds } from './layout'

// A rectangle of the map in SVG units: the part currently on screen
export interface Box {
  x: number
  y: number
  width: number
  height: number
}

// Zooming in past this makes seats larger than the screen needs
export const MAX_ZOOM = 8

const clamp = (value: number, min: number, max: number) =>
  Math.min(Math.max(value, min), max)

// Keeps `box` inside `full`, so panning can never lose the venue
function keepInside(full: Box, box: Box): Box {
  return {
    ...box,
    x: clamp(box.x, full.x, full.x + full.width - box.width),
    y: clamp(box.y, full.y, full.y + full.height - box.height),
  }
}

// Zoom by `factor` (2 = twice as close) around the current centre.
// The visible box always keeps the full map's proportions.
export function zoomBox(full: Box, current: Box, factor: number): Box {
  const width = clamp(current.width / factor, full.width / MAX_ZOOM, full.width)
  const height = width * (full.height / full.width)
  const centreX = current.x + current.width / 2
  const centreY = current.y + current.height / 2
  return keepInside(full, {
    x: centreX - width / 2,
    y: centreY - height / 2,
    width,
    height,
  })
}

// Move the view by (dx, dy) SVG units
export function panBox(full: Box, current: Box, dx: number, dy: number): Box {
  return keepInside(full, { ...current, x: current.x + dx, y: current.y + dy })
}

// The closest view that shows `bounds` (e.g. one section) with some margin
export function fitBounds(full: Box, bounds: Bounds, padding = 24): Box {
  const aspect = full.width / full.height
  let width = bounds.maxX - bounds.minX + padding * 2
  let height = bounds.maxY - bounds.minY + padding * 2
  // Grow the shorter side so the box matches the map's proportions
  if (width / height < aspect) width = height * aspect
  else height = width / aspect

  const zoomedWidth = clamp(width, full.width / MAX_ZOOM, full.width)
  const zoomedHeight = zoomedWidth / aspect
  const centreX = (bounds.minX + bounds.maxX) / 2
  const centreY = (bounds.minY + bounds.maxY) / 2
  return keepInside(full, {
    x: centreX - zoomedWidth / 2,
    y: centreY - zoomedHeight / 2,
    width: zoomedWidth,
    height: zoomedHeight,
  })
}

// How far in the view is (1 = the whole venue)
export function zoomLevel(full: Box, current: Box): number {
  return full.width / current.width
}
