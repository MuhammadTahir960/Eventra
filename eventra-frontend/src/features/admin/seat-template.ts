// Turns the admin's shorthand into the payload of POST /venues/{id}/seats/.
// "A-H" -> A..H, "1-12" -> 1..12, "AA, BB, CC" -> those three. Rows are
// trimmed, upper-cased, deduplicated and limited to the backend's 10 chars.

export interface SectionDraft {
  key: string
  name: string
  // Shorthand as typed, e.g. "A-H" or "1-20" or "A, B, C"
  rows: string
  seatsPerRow: string
}

export interface TemplatePayload {
  sections: {
    name: string
    rows: { row_label: string; seat_count: number }[]
  }[]
}

const MAX_ROWS_PER_RANGE = 100
const MAX_SEATS_PER_ROW = 500
// The backend's sanity limit for one template
export const MAX_TEMPLATE_SEATS = 2000

export function parseRowLabels(input: string): string[] | null {
  const labels: string[] = []
  for (const raw of input.split(',')) {
    const part = raw.trim().toUpperCase()
    if (!part) continue
    const range = /^([A-Z]|\d+)\s*-\s*([A-Z]|\d+)$/.exec(part)
    if (range) {
      const [, from, to] = range
      const numeric = /^\d+$/.test(from)
      if (numeric !== /^\d+$/.test(to)) return null
      const start = numeric ? Number(from) : from.charCodeAt(0)
      const end = numeric ? Number(to) : to.charCodeAt(0)
      if (end < start || end - start + 1 > MAX_ROWS_PER_RANGE) return null
      for (let code = start; code <= end; code += 1) {
        labels.push(numeric ? String(code) : String.fromCharCode(code))
      }
    } else if (/^[A-Z0-9]{1,10}$/.test(part)) {
      labels.push(part)
    } else {
      return null
    }
  }
  const unique = [...new Set(labels)]
  return unique.length > 0 ? unique : null
}

export type TemplateErrors = Record<string, string>

export function buildTemplate(
  sections: SectionDraft[],
  capacity: number,
): { payload: TemplatePayload | null; errors: TemplateErrors; total: number } {
  const errors: TemplateErrors = {}
  const names = new Set<string>()
  const built: TemplatePayload['sections'] = []
  let total = 0

  if (sections.length === 0) errors.sections = 'Add at least one section.'

  for (const section of sections) {
    const name = section.name.trim()
    if (!name) errors[`${section.key}-name`] = 'Name this section.'
    else if (name.length > 50)
      errors[`${section.key}-name`] = 'Use 50 characters or fewer.'
    else if (names.has(name.toLowerCase()))
      errors[`${section.key}-name`] = 'Section names must be different.'
    names.add(name.toLowerCase())

    const rows = parseRowLabels(section.rows)
    if (!rows)
      errors[`${section.key}-rows`] =
        'Use a range like A-H or 1-12, or a list like A, B, C.'

    const seats = Number(section.seatsPerRow)
    if (!Number.isInteger(seats) || seats < 1 || seats > MAX_SEATS_PER_ROW) {
      errors[`${section.key}-seats`] = `Enter 1 to ${MAX_SEATS_PER_ROW}.`
    }

    if (rows && Number.isInteger(seats) && seats >= 1) {
      total += rows.length * seats
      built.push({
        name,
        rows: rows.map((row_label) => ({ row_label, seat_count: seats })),
      })
    }
  }

  if (total > capacity)
    errors.total = `That's ${total} seats, more than the venue's capacity of ${capacity}.`
  else if (total > MAX_TEMPLATE_SEATS)
    errors.total = `That's ${total} seats; one template can hold at most ${MAX_TEMPLATE_SEATS}.`

  const valid = Object.keys(errors).length === 0
  return { payload: valid ? { sections: built } : null, errors, total }
}
