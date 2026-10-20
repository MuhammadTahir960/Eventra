// Colours for ticket tiers in the organizer's venue preview (the buyer's
// seat map uses neutral shades instead). Muted to sit with the brand palette.
// Spread around the colour wheel so neighbouring tiers are easy to tell apart.
export const TIER_COLORS = [
  'oklch(0.62 0.15 38)', // ember
  'oklch(0.56 0.09 155)', // moss
  'oklch(0.72 0.12 78)', // amber
  'oklch(0.55 0.07 245)', // slate blue
  'oklch(0.52 0.09 330)', // plum
  'oklch(0.6 0.07 195)', // teal
  'oklch(0.68 0.08 110)', // olive
  'oklch(0.5 0.05 60)', // walnut
] as const

export const MAX_TIERS = TIER_COLORS.length

export function tierColor(index: number): string {
  return TIER_COLORS[index % TIER_COLORS.length]
}
