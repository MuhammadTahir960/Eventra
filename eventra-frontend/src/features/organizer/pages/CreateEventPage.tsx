import { useMemo, useRef, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ErrorSummary, type ErrorItem } from '@/components/ErrorSummary'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import {
  useCategories,
  useLeagues,
  useTeams,
  useVenues,
} from '@/features/catalog/hooks'
import { useAuth } from '@/features/auth/auth-store'
import { VenueMapPreview } from '@/features/seating/components/VenueMapPreview'
import { useVenueTemplate } from '@/features/seating/hooks'
import { summarizeSections } from '@/features/seating/layout/summary'
import { ApiError } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import { TierEditor } from '../components/TierEditor'
import {
  CreateEventError,
  emptyProgress,
  newTierKey,
  submitEvent,
  suggestTiersFromSections,
  validateDraft,
  type CreateProgress,
  type DraftErrors,
  type EventDraft,
  type TierDraft,
} from '../create-event'
import { MAX_TIERS, tierColor } from '../tier-colors'
import { usePageTitle } from '@/lib/use-page-title'

const STEP_LABEL = {
  event: 'creating the event',
  tiers: 'adding the ticket tiers',
  sections: 'assigning sections to tiers',
  seats: 'generating the seats',
} as const

// Where each validation message lives on the page, for the error summary
function fieldIdFor(key: string): string {
  const fixed: Record<string, string> = {
    title: 'event-title',
    category: 'event-category',
    description: 'event-description',
    start: 'event-start',
    end: 'event-end',
    tiers: 'tiers',
    sections: 'section-assignments',
    home_team: 'event-home-team',
    away_team: 'event-away-team',
  }
  return fixed[key] ?? key
}

// Backend field names -> this form's field names
const SERVER_FIELD: Record<string, string> = {
  title: 'title',
  description: 'description',
  category: 'category',
  start_datetime: 'start',
  end_datetime: 'end',
  home_team: 'home_team',
  away_team: 'away_team',
}

// "2026-10-12T18:30" in the viewer's local time, for the picker's minimum
function localInputValue(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`
}

function blankDraft(): EventDraft {
  return {
    categoryId: '',
    title: '',
    description: '',
    start: '',
    end: '',
    tiers: [{ key: newTierKey(), name: '', price: '' }],
    assignments: {},
  }
}

export function CreateEventPage() {
  usePageTitle('Create event')
  const [params, setParams] = useSearchParams()
  const venues = useVenues()
  const categories = useCategories()
  // Sports fixtures are curated centrally: only admins may create them
  const isAdmin = useAuth().user?.role === 'admin'
  const teams = useTeams(isAdmin)
  const leagues = useLeagues(isAdmin)

  // The chosen venue lives in the URL so a reload keeps it. It is only used
  // if it is a real venue from the list.
  const requested = params.get('venue')
  const venue = isUuid(requested) ? venues.data?.byId.get(requested) : undefined
  const template = useVenueTemplate(venue?.id)

  const [draft, setDraft] = useState<EventDraft>(blankDraft)
  const [activeKey, setActiveKey] = useState(() => draft.tiers[0].key)
  const [errors, setErrors] = useState<DraftErrors>({})
  const [focusKey, setFocusKey] = useState(0)
  const [phase, setPhase] = useState<'idle' | 'working' | 'done'>('idle')
  const [failure, setFailure] = useState<CreateEventError | null>(null)
  const progress = useRef<CreateProgress>(emptyProgress())
  // True once the event exists on the server; the form is then locked
  const [created, setCreated] = useState(false)

  const sections = useMemo(
    () => (template.data ? summarizeSections(template.data) : []),
    [template.data],
  )
  const sectionNames = useMemo(() => sections.map((s) => s.name), [sections])
  const seatCount = template.data?.length ?? 0

  const suggestion = useMemo(
    () => suggestTiersFromSections(sectionNames),
    [sectionNames],
  )
  const pristine =
    draft.tiers.length === 1 &&
    !draft.tiers[0].name &&
    !draft.tiers[0].price &&
    Object.keys(draft.assignments).length === 0

  // Colour and label each section by the tier it was given
  const { sectionColors, sectionHints } = useMemo(() => {
    const colors: Record<string, string> = {}
    const hints: Record<string, string> = {}
    for (const [section, tierKey] of Object.entries(draft.assignments)) {
      const index = draft.tiers.findIndex((tier) => tier.key === tierKey)
      if (index >= 0) {
        colors[section] = tierColor(index)
        hints[section] =
          `${draft.tiers[index].name || `tier ${index + 1}`} tier`
      }
    }
    return { sectionColors: colors, sectionHints: hints }
  }, [draft.assignments, draft.tiers])

  const locked = phase === 'working' || created

  function patch(changes: Partial<EventDraft>) {
    setDraft((current) => ({ ...current, ...changes }))
  }

  function chooseVenue(id: string) {
    setParams(id ? { venue: id } : {}, { replace: true })
    // Sections differ between venues, so earlier assignments no longer apply
    patch({ assignments: {} })
  }

  function updateTier(
    key: string,
    changes: Partial<Pick<TierDraft, 'name' | 'price'>>,
  ) {
    setDraft((current) => ({
      ...current,
      tiers: current.tiers.map((tier) =>
        tier.key === key ? { ...tier, ...changes } : tier,
      ),
    }))
  }

  function addTier() {
    const tier = { key: newTierKey(), name: '', price: '' }
    setDraft((current) => ({ ...current, tiers: [...current.tiers, tier] }))
    setActiveKey(tier.key)
  }

  function removeTier(key: string) {
    setDraft((current) => {
      const tiers = current.tiers.filter((tier) => tier.key !== key)
      const assignments = Object.fromEntries(
        Object.entries(current.assignments).filter(
          ([, value]) => value !== key,
        ),
      )
      return { ...current, tiers, assignments }
    })
    if (activeKey === key) {
      const next = draft.tiers.find((tier) => tier.key !== key)
      if (next) setActiveKey(next.key)
    }
  }

  function assign(section: string, tierKey: string) {
    setDraft((current) => {
      const assignments = { ...current.assignments }
      if (tierKey) assignments[section] = tierKey
      else delete assignments[section]
      return { ...current, assignments }
    })
  }

  // Clicking a section on the map gives it the selected tier (or clears it)
  function handleMapClick(section: string) {
    assign(section, draft.assignments[section] === activeKey ? '' : activeKey)
  }

  function applySuggestion() {
    if (!suggestion) return
    setDraft((current) => ({
      ...current,
      tiers: suggestion.tiers,
      assignments: suggestion.assignments,
    }))
    setActiveKey(suggestion.tiers[0].key)
  }

  async function run() {
    if (!venue) return
    setFailure(null)
    setPhase('working')
    try {
      await submitEvent({ venueId: venue.id, draft }, progress.current)
      setCreated(true)
      setPhase('done')
    } catch (caught) {
      setPhase('idle')
      setCreated(Boolean(progress.current.eventId))
      if (!(caught instanceof CreateEventError)) return

      // Problems with the event's own fields go back onto those fields
      const inner = caught.cause
      if (
        caught.step === 'event' &&
        inner instanceof ApiError &&
        inner.status === 400
      ) {
        const serverErrors: DraftErrors = {}
        for (const [backend, field] of Object.entries(SERVER_FIELD)) {
          const message = inner.fieldErrors[backend]?.[0]
          if (message) serverErrors[field] = message
        }
        if (Object.keys(serverErrors).length > 0) {
          setErrors(serverErrors)
          setFocusKey((key) => key + 1)
          return
        }
      }
      setFailure(caught)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    // After a partial failure, retry continues from the failed step
    if (created) {
      void run()
      return
    }
    const found = validateDraft(draft, sectionNames)
    setErrors(found)
    if (Object.keys(found).length > 0) {
      setFocusKey((key) => key + 1)
      return
    }
    void run()
  }

  function startAnother() {
    progress.current = emptyProgress()
    const fresh = blankDraft()
    setDraft(fresh)
    setActiveKey(fresh.tiers[0].key)
    setErrors({})
    setFailure(null)
    setCreated(false)
    setPhase('idle')
  }

  const summary: ErrorItem[] = Object.entries(errors).map(([key, message]) => ({
    fieldId: fieldIdFor(key),
    message,
  }))

  if (phase === 'done' && progress.current.eventId) {
    const live = progress.current.eventStatus === 'approved'
    return (
      <section className="flex max-w-xl flex-col gap-4">
        <h1 className="font-display text-[clamp(2rem,4vw,2.5rem)] leading-tight">
          Event created
        </h1>
        <Notice tone="success">
          {live
            ? 'Your event is live and its seats are ready to book.'
            : 'Your event was submitted for admin approval. It goes on sale once approved.'}
        </Notice>
        <div className="flex flex-wrap gap-3">
          <ButtonLink
            variant="ink"
            size="lg"
            to={`/events/${progress.current.eventId}`}
          >
            View event
          </ButtonLink>
          <Button variant="outline" size="lg" onClick={startAnother}>
            Create another
          </Button>
        </div>
      </section>
    )
  }

  const noSeats = template.isSuccess && seatCount === 0

  return (
    <section className="flex flex-col gap-8">
      <h1 className="font-display text-[clamp(2rem,4vw,2.5rem)] leading-tight">
        Create event
      </h1>

      <div className="max-w-md">
        <FormField
          id="event-venue"
          label="Venue"
          hint="Its seat map appears as soon as you choose it."
        >
          {(control) => (
            <NativeSelect
              {...control}
              value={venue?.id ?? ''}
              onChange={(event) => chooseVenue(event.target.value)}
              disabled={venues.isPending || locked}
            >
              <option value="">
                {venues.isPending ? 'Loading venues…' : 'Select a venue'}
              </option>
              {venues.data?.list.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}, {item.city}
                </option>
              ))}
            </NativeSelect>
          )}
        </FormField>
      </div>

      {venues.isError && (
        <Notice tone="error">
          Could not load venues. Reload to try again.
        </Notice>
      )}

      {venue && (
        <div className="grid gap-8 lg:grid-cols-2">
          {/* Map first on phones; pinned beside the form on wide screens */}
          <div className="space-y-4 lg:sticky lg:top-6 lg:order-2 lg:self-start">
            <div>
              <h2 className="text-lg font-semibold tracking-tight">
                {venue.name}
              </h2>
              <p className="text-sm text-muted-foreground">
                {venue.address}, {venue.city}, {venue.country}
              </p>
              {template.isSuccess && seatCount > 0 && (
                <p className="mt-1 text-sm">
                  <span className="tabular-nums">{seatCount}</span> seats in{' '}
                  <span className="tabular-nums">{sections.length}</span>{' '}
                  {sections.length === 1 ? 'section' : 'sections'}, capacity{' '}
                  <span className="tabular-nums">{venue.capacity}</span>
                </p>
              )}
            </div>

            {template.isPending && (
              <p role="status" className="text-sm text-muted-foreground">
                Loading seat map…
              </p>
            )}
            {template.isError && (
              <Notice tone="error">
                {template.error instanceof ApiError
                  ? template.error.message
                  : 'Could not load this venue’s seat map.'}
              </Notice>
            )}
            {noSeats && (
              <Notice>
                This venue has no seat map yet, so events here can't have
                assigned seating. Ask an admin to set up its seats first.
              </Notice>
            )}

            {template.isSuccess && seatCount > 0 && (
              <>
                <VenueMapPreview
                  seats={template.data}
                  shape={venue.layout_shape}
                  sectionColors={sectionColors}
                  sectionHints={sectionHints}
                  onSectionSelect={locked ? undefined : handleMapClick}
                  showTable={false}
                />
                <ul
                  aria-label="Tier colours"
                  className="flex flex-wrap gap-x-4 gap-y-1 text-sm"
                >
                  {draft.tiers.map((tier, index) => (
                    <li key={tier.key} className="flex items-center gap-1.5">
                      <span
                        aria-hidden="true"
                        className="size-3 rounded-full border"
                        style={{ background: tierColor(index) }}
                      />
                      {tier.name || `Tier ${index + 1}`}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>

          {template.isSuccess && seatCount > 0 && (
            <form
              onSubmit={handleSubmit}
              noValidate
              className="space-y-6 lg:order-1"
            >
              <ErrorSummary errors={summary} focusKey={focusKey} />

              {created && !failure && <Notice>Finishing setup…</Notice>}
              {failure && (
                <Notice tone="error">
                  {failure.step === 'event'
                    ? `The event could not be created: ${failure.message}`
                    : `The event was created, but ${STEP_LABEL[failure.step]} failed: ${failure.message} Retry to finish; nothing will be duplicated.`}
                </Notice>
              )}

              <div className="space-y-4">
                <h2 className="text-lg font-semibold tracking-tight">
                  Event details
                </h2>

                <FormField id="event-title" label="Title" error={errors.title}>
                  {(control) => (
                    <Input
                      {...control}
                      value={draft.title}
                      maxLength={100}
                      disabled={locked}
                      onChange={(event) => patch({ title: event.target.value })}
                    />
                  )}
                </FormField>

                {isAdmin && (
                  <fieldset className="flex flex-col gap-4" disabled={locked}>
                    <legend className="mb-1.5 text-sm font-medium">Type</legend>
                    <div className="inline-flex w-fit rounded-full border border-border bg-card p-1">
                      {(['general', 'match'] as const).map((type) => {
                        const active =
                          (type === 'match') === Boolean(draft.match)
                        return (
                          <button
                            key={type}
                            type="button"
                            aria-pressed={active}
                            onClick={() =>
                              patch({
                                match:
                                  type === 'match'
                                    ? {
                                        leagueId: '',
                                        homeTeamId: '',
                                        awayTeamId: '',
                                      }
                                    : null,
                              })
                            }
                            className={
                              active
                                ? 'h-8 rounded-full bg-ink px-4 text-sm text-paper'
                                : 'h-8 rounded-full px-4 text-sm text-muted-foreground hover:text-foreground'
                            }
                          >
                            {type === 'general' ? 'Event' : 'Sports match'}
                          </button>
                        )
                      })}
                    </div>
                    {draft.match && (
                      <div className="grid gap-4 sm:grid-cols-3">
                        <FormField id="event-league" label="League (optional)">
                          {(control) => (
                            <NativeSelect
                              {...control}
                              value={draft.match?.leagueId ?? ''}
                              onChange={(event) =>
                                draft.match &&
                                patch({
                                  match: {
                                    ...draft.match,
                                    leagueId: event.target.value,
                                  },
                                })
                              }
                            >
                              <option value="">No league</option>
                              {[...(leagues.data?.values() ?? [])].map(
                                (league) => (
                                  <option key={league.id} value={league.id}>
                                    {league.name}
                                  </option>
                                ),
                              )}
                            </NativeSelect>
                          )}
                        </FormField>
                        {(['homeTeamId', 'awayTeamId'] as const).map((side) => (
                          <FormField
                            key={side}
                            id={
                              side === 'homeTeamId'
                                ? 'event-home-team'
                                : 'event-away-team'
                            }
                            label={
                              side === 'homeTeamId' ? 'Home team' : 'Away team'
                            }
                            error={
                              side === 'homeTeamId'
                                ? errors.home_team
                                : errors.away_team
                            }
                          >
                            {(control) => (
                              <NativeSelect
                                {...control}
                                value={draft.match?.[side] ?? ''}
                                onChange={(event) =>
                                  draft.match &&
                                  patch({
                                    match: {
                                      ...draft.match,
                                      [side]: event.target.value,
                                    },
                                  })
                                }
                              >
                                <option value="">Select a team</option>
                                {[...(teams.data?.values() ?? [])].map(
                                  (team) => (
                                    <option key={team.id} value={team.id}>
                                      {team.name}
                                    </option>
                                  ),
                                )}
                              </NativeSelect>
                            )}
                          </FormField>
                        ))}
                      </div>
                    )}
                  </fieldset>
                )}

                <FormField
                  id="event-category"
                  label="Category"
                  error={errors.category}
                >
                  {(control) => (
                    <NativeSelect
                      {...control}
                      value={draft.categoryId}
                      disabled={locked}
                      onChange={(event) =>
                        patch({ categoryId: event.target.value })
                      }
                    >
                      <option value="">Select a category</option>
                      {categories.data?.list.map((category) => (
                        <option key={category.id} value={category.id}>
                          {category.name}
                        </option>
                      ))}
                    </NativeSelect>
                  )}
                </FormField>

                <FormField
                  id="event-description"
                  label="Description"
                  error={errors.description}
                >
                  {(control) => (
                    <Textarea
                      {...control}
                      value={draft.description}
                      maxLength={5000}
                      disabled={locked}
                      onChange={(event) =>
                        patch({ description: event.target.value })
                      }
                    />
                  )}
                </FormField>

                <div className="grid gap-4 sm:grid-cols-2">
                  <FormField
                    id="event-start"
                    label="Starts"
                    error={errors.start}
                  >
                    {(control) => (
                      <Input
                        {...control}
                        type="datetime-local"
                        value={draft.start}
                        min={localInputValue(new Date())}
                        disabled={locked}
                        onChange={(event) =>
                          patch({ start: event.target.value })
                        }
                      />
                    )}
                  </FormField>
                  <FormField id="event-end" label="Ends" error={errors.end}>
                    {(control) => (
                      <Input
                        {...control}
                        type="datetime-local"
                        value={draft.end}
                        min={draft.start || localInputValue(new Date())}
                        disabled={locked}
                        onChange={(event) => patch({ end: event.target.value })}
                      />
                    )}
                  </FormField>
                </div>
              </div>

              <TierEditor
                tiers={draft.tiers}
                activeKey={activeKey}
                assignments={draft.assignments}
                sections={sections}
                errors={errors}
                disabled={locked}
                onSuggest={suggestion && pristine ? applySuggestion : null}
                onActiveChange={setActiveKey}
                onTierChange={updateTier}
                onAddTier={addTier}
                onRemoveTier={removeTier}
                onAssign={assign}
              />
              {draft.tiers.length >= MAX_TIERS && (
                <p className="text-xs text-muted-foreground">
                  You can add up to {MAX_TIERS} tiers.
                </p>
              )}

              <Button
                type="submit"
                variant="ink"
                size="lg"
                className="w-full"
                disabled={phase === 'working'}
              >
                {phase === 'working'
                  ? 'Creating…'
                  : created
                    ? 'Retry'
                    : 'Create event'}
              </Button>
            </form>
          )}
        </div>
      )}
    </section>
  )
}
