import { describe, expect, it } from 'vitest'
import {
  fitBounds,
  MAX_ZOOM,
  panBox,
  zoomBox,
  zoomLevel,
  type Box,
} from './viewport'

const FULL: Box = { x: -400, y: -300, width: 800, height: 600 }

const inside = (box: Box) =>
  box.x >= FULL.x - 1e-9 &&
  box.y >= FULL.y - 1e-9 &&
  box.x + box.width <= FULL.x + FULL.width + 1e-9 &&
  box.y + box.height <= FULL.y + FULL.height + 1e-9

describe('zoomBox', () => {
  it('zooming in 2x halves the visible area, around the centre', () => {
    const zoomed = zoomBox(FULL, FULL, 2)
    expect(zoomed.width).toBe(400)
    expect(zoomed.height).toBe(300)
    expect(zoomed.x + zoomed.width / 2).toBeCloseTo(0)
    expect(zoomed.y + zoomed.height / 2).toBeCloseTo(0)
  })

  it('cannot zoom out past the whole venue', () => {
    expect(zoomBox(FULL, FULL, 0.5)).toEqual(FULL)
  })

  it('cannot zoom in past the maximum', () => {
    let box = FULL
    for (let i = 0; i < 20; i += 1) box = zoomBox(FULL, box, 2)
    expect(zoomLevel(FULL, box)).toBeCloseTo(MAX_ZOOM)
  })

  it('keeps the map proportions', () => {
    const zoomed = zoomBox(FULL, FULL, 3)
    expect(zoomed.width / zoomed.height).toBeCloseTo(FULL.width / FULL.height)
  })
})

describe('panBox', () => {
  const zoomed = zoomBox(FULL, FULL, 4)

  it('moves the view', () => {
    const moved = panBox(FULL, zoomed, 50, 20)
    expect(moved.x).toBeCloseTo(zoomed.x + 50)
    expect(moved.y).toBeCloseTo(zoomed.y + 20)
  })

  it('never leaves the venue', () => {
    expect(inside(panBox(FULL, zoomed, 5000, 5000))).toBe(true)
    expect(inside(panBox(FULL, zoomed, -5000, -5000))).toBe(true)
  })
})

describe('fitBounds', () => {
  it('shows a section with margin, in the map proportions', () => {
    const section = { minX: 100, minY: -50, maxX: 200, maxY: 20 }
    const box = fitBounds(FULL, section)

    expect(box.width / box.height).toBeCloseTo(FULL.width / FULL.height)
    expect(box.x).toBeLessThanOrEqual(section.minX)
    expect(box.x + box.width).toBeGreaterThanOrEqual(section.maxX)
    expect(box.y).toBeLessThanOrEqual(section.minY)
    expect(box.y + box.height).toBeGreaterThanOrEqual(section.maxY)
    expect(inside(box)).toBe(true)
  })

  it('stays inside the venue for a section at the edge', () => {
    const edge = { minX: 330, minY: 230, maxX: 400, maxY: 300 }
    expect(inside(fitBounds(FULL, edge))).toBe(true)
  })

  it('never zooms out beyond the whole venue', () => {
    const huge = { minX: -1000, minY: -1000, maxX: 1000, maxY: 1000 }
    expect(fitBounds(FULL, huge).width).toBe(FULL.width)
  })
})
