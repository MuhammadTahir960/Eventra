import { apiFetch, ApiError } from '@/lib/api-client'
import type { EventItem, TicketTier } from '@/features/events/types'

// ---------- the form's data ----------

export interface TierDraft {
  // Local id, only used to link sections to tiers before the backend has ids
  key: string
  name: string
  // Kept as text while typing; validated and sent as a decimal string
  price: string
}

export interface EventDraft {
  categoryId: string
  title: string
  description: string
  // <input type="datetime-local"> values, e.g. "2026-11-01T18:30"
  start: string
  end: string
  tiers: TierDraft[]
  // section name -> tier key
  assignments: Record<string, string>
  // Set for a sports match (admins only: the backend refuses organizers)
  match?: MatchDraft | null
}

export interface MatchDraft {
  // Optional: a friendly or a cup tie may have no league
  leagueId: string
  homeTeamId: string
  awayTeamId: string
}

export type DraftErrors = Record<string, string>

let tierCounter = 0
export function newTierKey(): string {
  tierCounter += 1
  return `tier-${tierCounter}`
}

// ---------- validation (mirrors the backend; the server still has the final say) ----------

const PRICE_PATTERN = /^\d{1,8}(\.\d{1,2})?$/

export function validateDraft(
  draft: EventDraft,
  venueSections: string[],
  now: Date = new Date(),
): DraftErrors {
  const errors: DraftErrors = {}

  const title = draft.title.trim()
  if (!title) errors.title = 'Enter a title.'
  else if (title.length > 100) errors.title = 'Use 100 characters or fewer.'

  if (!draft.categoryId) errors.category = 'Choose a category.'

  const description = draft.description.trim()
  if (!description) errors.description = 'Describe the event.'
  else if (description.length > 5000) {
    errors.description = 'Use 5000 characters or fewer.'
  }

  const start = draft.start ? new Date(draft.start) : null
  const end = draft.end ? new Date(draft.end) : null
  if (!start || Number.isNaN(start.getTime()))
    errors.start = 'Choose a start time.'
  else if (start <= now) errors.start = 'The start time must be in the future.'
  if (!end || Number.isNaN(end.getTime())) errors.end = 'Choose an end time.'
  else if (start && !Number.isNaN(start.getTime()) && end <= start) {
    errors.end = 'The end time must be after the start.'
  }

  if (draft.match) {
    if (!draft.match.homeTeamId) errors.home_team = 'Choose the home team.'
    if (!draft.match.awayTeamId) errors.away_team = 'Choose the away team.'
    else if (draft.match.awayTeamId === draft.match.homeTeamId) {
      errors.away_team = 'Pick two different teams.'
    }
  }

  if (draft.tiers.length === 0) errors.tiers = 'Add at least one ticket tier.'

  const seenNames = new Set<string>()
  for (const tier of draft.tiers) {
    const name = tier.name.trim()
    if (!name) errors[`tier-${tier.key}-name`] = 'Name this tier.'
    else if (name.length > 100) {
      errors[`tier-${tier.key}-name`] = 'Use 100 characters or fewer.'
    } else if (seenNames.has(name.toLowerCase())) {
      errors[`tier-${tier.key}-name`] = 'Tier names must be different.'
    }
    seenNames.add(name.toLowerCase())

    if (!PRICE_PATTERN.test(tier.price.trim()) || Number(tier.price) < 0.01) {
      errors[`tier-${tier.key}-price`] = 'Enter a price of at least 0.01.'
    }
  }

  // Seat generation needs every section priced, and an unused tier is a mistake
  const tierKeys = new Set(draft.tiers.map((tier) => tier.key))
  const unassigned = venueSections.filter(
    (section) => !tierKeys.has(draft.assignments[section]),
  )
  if (unassigned.length > 0) {
    errors.sections = `Assign a tier to every section. Missing: ${unassigned.join(', ')}.`
  }
  for (const tier of draft.tiers) {
    const used = venueSections.some(
      (section) => draft.assignments[section] === tier.key,
    )
    if (!used && !errors[`tier-${tier.key}-name`]) {
      errors[`tier-${tier.key}-name`] =
        'No section uses this tier. Assign one or remove it.'
    }
  }

  return errors
}

// If sections are named like classes (VIP, Business, Economy), offer one tier
// per section name. Skipped for numbered or very large venues.
export function suggestTiersFromSections(sections: string[]): {
  tiers: TierDraft[]
  assignments: Record<string, string>
} | null {
  const usable =
    sections.length >= 2 &&
    sections.length <= 8 &&
    sections.every((name) => !/^\d+$/.test(name))
  if (!usable) return null

  const tiers = sections.map((name) => ({ key: newTierKey(), name, price: '' }))
  const assignments: Record<string, string> = {}
  tiers.forEach((tier) => {
    assignments[tier.name] = tier.key
  })
  return { tiers, assignments }
}

// ---------- submitting: four dependent calls, resumable ----------

export interface CreateProgress {
  eventId?: string
  eventStatus?: EventItem['status']
  // tier key -> backend tier id
  tierIds: Record<string, string>
  // sections already mapped to their tier
  mapped: string[]
  instantiated: boolean
}

export const emptyProgress = (): CreateProgress => ({
  tierIds: {},
  mapped: [],
  instantiated: false,
})

export type CreateStep = 'event' | 'tiers' | 'sections' | 'seats'

// Says which step failed, so the page can explain and the retry resumes there
export class CreateEventError extends Error {
  step: CreateStep
  cause: unknown

  constructor(step: CreateStep, cause: unknown) {
    super(cause instanceof Error ? cause.message : 'Something went wrong.')
    this.name = 'CreateEventError'
    this.step = step
    this.cause = cause
  }
}

export interface SubmitInput {
  venueId: string
  draft: EventDraft
}

// Creates the event, its tiers, the section mappings and the seats, in the
// order the backend requires. The backend can't do this atomically, so
// `progress` records each finished step and is updated in place; calling
// this again after a failure continues from where it stopped instead of
// creating duplicates.
export async function submitEvent(
  { venueId, draft }: SubmitInput,
  progress: CreateProgress,
): Promise<CreateProgress> {
  let step: CreateStep = 'event'
  try {
    if (!progress.eventId) {
      const created = await apiFetch<EventItem>('/events/', {
        method: 'POST',
        body: {
          venue: venueId,
          category: draft.categoryId,
          title: draft.title.trim(),
          description: draft.description.trim(),
          ...(draft.match
            ? {
                event_type: 'sports_match',
                league: draft.match.leagueId || null,
                home_team: draft.match.homeTeamId,
                away_team: draft.match.awayTeamId,
              }
            : { event_type: 'general' }),
          is_seated: true,
          start_datetime: new Date(draft.start).toISOString(),
          end_datetime: new Date(draft.end).toISOString(),
        },
      })
      progress.eventId = created.id
      progress.eventStatus = created.status
    }
    const eventId = progress.eventId

    step = 'tiers'
    for (const tier of draft.tiers) {
      if (progress.tierIds[tier.key]) continue
      const created = await apiFetch<TicketTier>(
        `/events/${eventId}/ticket-tiers/`,
        {
          method: 'POST',
          body: {
            name: tier.name.trim(),
            price: Number(tier.price).toFixed(2),
          },
        },
      )
      progress.tierIds[tier.key] = created.id
    }

    step = 'sections'
    for (const [section, tierKey] of Object.entries(draft.assignments)) {
      if (progress.mapped.includes(section)) continue
      await apiFetch(
        `/events/${eventId}/ticket-tiers/${progress.tierIds[tierKey]}/sections/`,
        { method: 'POST', body: { section } },
      )
      progress.mapped.push(section)
    }

    step = 'seats'
    if (!progress.instantiated) {
      await apiFetch(`/events/${eventId}/seats/instantiate/`, {
        method: 'POST',
      })
      progress.instantiated = true
    }
    return progress
  } catch (error) {
    // A 409 on seats means a previous attempt already generated them
    if (step === 'seats' && error instanceof ApiError && error.status === 409) {
      progress.instantiated = true
      return progress
    }
    throw new CreateEventError(step, error)
  }
}
