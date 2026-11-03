export type DisplayState = 'available' | 'selected' | 'held' | 'booked'

export const STATE_TEXT: Record<DisplayState, string> = {
  available: 'available',
  selected: 'selected',
  held: 'held by another buyer',
  booked: 'sold',
}

// Tiers are told apart by warm neutral shades and their labels, never by
// extra hues, so the ember of a selected seat is the only colour on the map
export const TIER_SHADES = [
  '#f1efe9',
  '#e6e2d8',
  '#dbd6c8',
  '#d0cab9',
  '#c5beab',
]

// Movement below this many pixels is a tap on a seat, not a drag of the map
export const DRAG_THRESHOLD_PX = 5
export const ZOOM_STEP = 1.6
