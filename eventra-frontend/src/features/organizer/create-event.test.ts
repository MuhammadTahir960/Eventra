import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from '@/lib/api-client'
import {
  CreateEventError,
  emptyProgress,
  submitEvent,
  suggestTiersFromSections,
  validateDraft,
  type EventDraft,
} from './create-event'

vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiFetch: vi.fn(),
}))
const apiFetchMock = vi.mocked(apiFetch)

const NOW = new Date('2026-10-12T10:00:00')

function makeDraft(overrides: Partial<EventDraft> = {}): EventDraft {
  return {
    categoryId: 'cat-1',
    title: 'Derby',
    description: 'A big match',
    start: '2026-11-01T18:00',
    end: '2026-11-01T21:00',
    tiers: [
      { key: 'a', name: 'VIP', price: '120.00' },
      { key: 'b', name: 'Economy', price: '40' },
    ],
    assignments: { North: 'a', South: 'b' },
    ...overrides,
  }
}

describe('validateDraft', () => {
  it('accepts a complete draft', () => {
    expect(validateDraft(makeDraft(), ['North', 'South'], NOW)).toEqual({})
  })

  it('requires the basic fields', () => {
    const errors = validateDraft(
      makeDraft({ title: ' ', categoryId: '', description: '' }),
      ['North', 'South'],
      NOW,
    )
    expect(errors).toHaveProperty('title')
    expect(errors).toHaveProperty('category')
    expect(errors).toHaveProperty('description')
  })

  it('rejects a start in the past and an end before the start', () => {
    const errors = validateDraft(
      makeDraft({ start: '2026-10-01T18:00', end: '2026-09-30T18:00' }),
      ['North', 'South'],
      NOW,
    )
    expect(errors.start).toMatch(/future/)
    expect(errors.end).toMatch(/after the start/)
  })

  it.each(['0', '0.00', '-5', 'abc', '1.234', ''])(
    'rejects the price %j',
    (price) => {
      const errors = validateDraft(
        makeDraft({
          tiers: [{ key: 'a', name: 'VIP', price }],
          assignments: { North: 'a', South: 'a' },
        }),
        ['North', 'South'],
        NOW,
      )
      expect(errors).toHaveProperty('tier-a-price')
    },
  )

  it('rejects duplicate tier names', () => {
    const errors = validateDraft(
      makeDraft({
        tiers: [
          { key: 'a', name: 'VIP', price: '10' },
          { key: 'b', name: 'vip', price: '20' },
        ],
      }),
      ['North', 'South'],
      NOW,
    )
    expect(errors).toHaveProperty('tier-b-name')
  })

  it('requires every venue section to have a tier', () => {
    const errors = validateDraft(
      makeDraft({ assignments: { North: 'a' } }),
      ['North', 'South'],
      NOW,
    )
    expect(errors.sections).toMatch(/South/)
  })

  it('flags a tier that no section uses', () => {
    const errors = validateDraft(
      makeDraft({ assignments: { North: 'a', South: 'a' } }),
      ['North', 'South'],
      NOW,
    )
    expect(errors).toHaveProperty('tier-b-name')
  })

  it('caps the title at 100 characters, like the backend', () => {
    const at = validateDraft(
      makeDraft({ title: 'A'.repeat(100) }),
      ['North', 'South'],
      NOW,
    )
    const over = validateDraft(
      makeDraft({ title: 'A'.repeat(101) }),
      ['North', 'South'],
      NOW,
    )
    expect(at).not.toHaveProperty('title')
    expect(over.title).toBe('Use 100 characters or fewer.')
  })

  it('needs two different teams for a sports match', () => {
    const missing = validateDraft(
      makeDraft({ match: { leagueId: '', homeTeamId: '', awayTeamId: '' } }),
      ['North', 'South'],
      NOW,
    )
    expect(missing).toHaveProperty('home_team')
    expect(missing).toHaveProperty('away_team')

    const same = validateDraft(
      makeDraft({
        match: { leagueId: '', homeTeamId: 't1', awayTeamId: 't1' },
      }),
      ['North', 'South'],
      NOW,
    )
    expect(same.away_team).toBe('Pick two different teams.')
  })

  it('requires at least one tier', () => {
    const errors = validateDraft(
      makeDraft({ tiers: [], assignments: {} }),
      ['North'],
      NOW,
    )
    expect(errors).toHaveProperty('tiers')
  })
})

describe('suggestTiersFromSections', () => {
  it('makes one tier per class-like section name', () => {
    const suggestion = suggestTiersFromSections(['VIP', 'Business', 'Economy'])
    expect(suggestion?.tiers.map((t) => t.name)).toEqual([
      'VIP',
      'Business',
      'Economy',
    ])
    // Each section is assigned to the tier with its own name
    for (const tier of suggestion!.tiers) {
      expect(suggestion!.assignments[tier.name]).toBe(tier.key)
    }
  })

  it('does not suggest for numbered sections or one section', () => {
    expect(suggestTiersFromSections(['101', '102', '201'])).toBeNull()
    expect(suggestTiersFromSections(['VIP'])).toBeNull()
  })

  it('does not suggest for very large venues', () => {
    const many = Array.from({ length: 9 }, (_, i) => `Block ${i}`)
    expect(suggestTiersFromSections(many)).toBeNull()
  })
})

describe('submitEvent', () => {
  beforeEach(() => {
    apiFetchMock.mockReset()
  })

  // Answers each backend call the way the real API would
  function happyPath() {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === '/events/')
        return { id: 'evt-1', status: 'pending_approval' }
      if (path.endsWith('/ticket-tiers/')) {
        return { id: `tier-${apiFetchMock.mock.calls.length}` }
      }
      return {}
    })
  }

  it('creates the event, tiers, section mappings and seats in order', async () => {
    happyPath()
    const progress = await submitEvent(
      { venueId: 'v1', draft: makeDraft() },
      emptyProgress(),
    )

    const paths = apiFetchMock.mock.calls.map((call) => call[0])
    expect(paths[0]).toBe('/events/')
    expect(paths.filter((p) => p.endsWith('/ticket-tiers/'))).toHaveLength(2)
    expect(paths.filter((p) => p.endsWith('/sections/'))).toHaveLength(2)
    expect(paths.at(-1)).toBe('/events/evt-1/seats/instantiate/')
    expect(progress.eventStatus).toBe('pending_approval')
    expect(progress.instantiated).toBe(true)
  })

  it('sends prices as two-decimal strings and the event as a seated general event', async () => {
    happyPath()
    await submitEvent({ venueId: 'v1', draft: makeDraft() }, emptyProgress())

    const eventBody = apiFetchMock.mock.calls[0][1]?.body as Record<
      string,
      unknown
    >
    expect(eventBody).toMatchObject({
      venue: 'v1',
      category: 'cat-1',
      event_type: 'general',
      is_seated: true,
    })
    const tierBodies = apiFetchMock.mock.calls
      .filter((call) => call[0].endsWith('/ticket-tiers/'))
      .map((call) => (call[1]?.body as { price: string } | undefined)?.price)
    expect(tierBodies).toEqual(['120.00', '40.00'])
  })

  it('sends a match with its teams, and no league as null', async () => {
    happyPath()
    await submitEvent(
      {
        venueId: 'v1',
        draft: makeDraft({
          match: { leagueId: '', homeTeamId: 't1', awayTeamId: 't2' },
        }),
      },
      emptyProgress(),
    )
    expect(apiFetchMock.mock.calls[0][1]?.body).toMatchObject({
      event_type: 'sports_match',
      league: null,
      home_team: 't1',
      away_team: 't2',
    })
  })

  it('resumes after a failure without creating anything twice', async () => {
    const draft = makeDraft()
    const progress = emptyProgress()

    // First attempt: everything works until the second tier is created
    let tierCalls = 0
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === '/events/') return { id: 'evt-1', status: 'approved' }
      if (path.endsWith('/ticket-tiers/')) {
        tierCalls += 1
        if (tierCalls === 2) throw new ApiError(500, 'Server error')
        return { id: 'tier-1' }
      }
      return {}
    })
    await expect(
      submitEvent({ venueId: 'v1', draft }, progress),
    ).rejects.toMatchObject({ name: 'CreateEventError', step: 'tiers' })
    expect(progress.eventId).toBe('evt-1')
    expect(progress.tierIds).toEqual({ a: 'tier-1' })

    // Retry: only the missing work is sent
    apiFetchMock.mockReset()
    apiFetchMock.mockImplementation(async (path: string) =>
      path.endsWith('/ticket-tiers/') ? { id: 'tier-2' } : {},
    )
    await submitEvent({ venueId: 'v1', draft }, progress)

    const paths = apiFetchMock.mock.calls.map((call) => call[0])
    expect(paths).not.toContain('/events/')
    expect(paths.filter((p) => p.endsWith('/ticket-tiers/'))).toHaveLength(1)
    expect(progress.instantiated).toBe(true)
  })

  it('treats "seats already generated" (409) as success on retry', async () => {
    const progress = emptyProgress()
    apiFetchMock.mockImplementation(async (path: string) => {
      if (path === '/events/') return { id: 'evt-1', status: 'approved' }
      if (path.endsWith('/ticket-tiers/')) return { id: 't' }
      if (path.endsWith('/instantiate/'))
        throw new ApiError(409, 'Already done')
      return {}
    })
    await expect(
      submitEvent({ venueId: 'v1', draft: makeDraft() }, progress),
    ).resolves.toMatchObject({ instantiated: true })
  })

  it('reports which step failed', async () => {
    apiFetchMock.mockRejectedValueOnce(new ApiError(400, 'Bad dates'))
    const error = await submitEvent(
      { venueId: 'v1', draft: makeDraft() },
      emptyProgress(),
    ).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(CreateEventError)
    expect((error as CreateEventError).step).toBe('event')
    expect((error as CreateEventError).message).toBe('Bad dates')
  })
})
