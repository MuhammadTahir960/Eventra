const graphemes = new Intl.Segmenter(undefined, { granularity: 'grapheme' })

// First letter of a name or title, for monograms. Works by grapheme, so an
// emoji or a combining accent is never cut in half, and skips leading
// non-letters ("🎷 Late Jazz" -> "L", "#Summer" -> "S").
export function initial(text: string, fallback = '?'): string {
  for (const { segment } of graphemes.segment(text)) {
    if (/\p{L}/u.test(segment)) return segment.toLocaleUpperCase()
  }
  return fallback
}
