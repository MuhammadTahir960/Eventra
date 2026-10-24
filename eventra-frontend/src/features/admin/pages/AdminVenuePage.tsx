import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { useVenues } from '@/features/catalog/hooks'
import type { Venue } from '@/features/catalog/types'
import { VenueMapPreview } from '@/features/seating/components/VenueMapPreview'
import { useVenueTemplate } from '@/features/seating/hooks'
import type { LayoutSeatInput } from '@/features/seating/layout/layout'
import { ApiError, apiFetch } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import {
  buildTemplate,
  parseRowLabels,
  type SectionDraft,
} from '../seat-template'
import { usePageTitle } from '@/lib/use-page-title'

const SHAPES = [
  ['oval', 'Oval (stadium)'],
  ['circle', 'Circle (arena)'],
  ['rectangle', 'Rectangle (hall)'],
  ['u_shape', 'U-shape'],
  ['semicircle', 'Semicircle (theatre)'],
] as const

// Matches the backend's shared image validators (apps/common/validators.py)
const PHOTO_TYPES = 'image/jpeg,image/png,image/webp'
const MAX_PHOTO_MB = 5

const fieldErrorsOf = (caught: unknown): Record<string, string> =>
  caught instanceof ApiError
    ? Object.fromEntries(
        Object.entries(caught.fieldErrors).map(([key, messages]) => [
          key,
          messages[0],
        ]),
      )
    : {}

function DetailsForm({ venue }: { venue: Venue | undefined }) {
  const client = useQueryClient()
  const navigate = useNavigate()
  const [values, setValues] = useState({
    name: venue?.name ?? '',
    address: venue?.address ?? '',
    city: venue?.city ?? '',
    country: venue?.country ?? '',
    capacity: venue ? String(venue.capacity) : '',
    layout_shape: venue?.layout_shape ?? 'oval',
  })
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!photo) return setPreview(null)
    const url = URL.createObjectURL(photo)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [photo])

  const save = useMutation({
    mutationFn: () => {
      // Multipart, because the photo is a file; the other fields go along
      const body = new FormData()
      for (const [key, value] of Object.entries(values))
        body.append(key, value.trim())
      if (photo) body.append('photo', photo)
      return venue
        ? apiFetch<Venue>(`/venues/${venue.id}/`, { method: 'PATCH', body })
        : apiFetch<Venue>('/venues/', { method: 'POST', body })
    },
    onSuccess: (result) => {
      void client.invalidateQueries({ queryKey: ['catalog', 'venues'] })
      setPhoto(null)
      setSaved(true)
      if (!venue) navigate(`/admin/venues/${result.id}`, { replace: true })
    },
    onError: (caught) => setErrors(fieldErrorsOf(caught)),
  })

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const clientErrors: Record<string, string> = {}
    if (values.name.trim().length < 2)
      clientErrors.name = 'Enter the venue name.'
    if (!values.address.trim()) clientErrors.address = 'Enter the address.'
    if (!values.city.trim()) clientErrors.city = 'Enter the city.'
    if (!values.country.trim()) clientErrors.country = 'Enter the country.'
    const capacity = Number(values.capacity)
    if (!Number.isInteger(capacity) || capacity < 1)
      clientErrors.capacity = 'Enter a whole number of seats.'
    if (photo && photo.size > MAX_PHOTO_MB * 1024 * 1024)
      clientErrors.photo = `Use an image under ${MAX_PHOTO_MB} MB.`
    setErrors(clientErrors)
    setSaved(false)
    if (Object.keys(clientErrors).length === 0) save.mutate()
  }

  const text = (key: keyof typeof values, label: string, max: number) => (
    <FormField id={`venue-${key}`} label={label} error={errors[key]}>
      {(control) => (
        <Input
          {...control}
          maxLength={max}
          value={values[key]}
          onChange={(e) => setValues({ ...values, [key]: e.target.value })}
        />
      )}
    </FormField>
  )

  const shownPhoto = preview ?? venue?.photo ?? null

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]"
    >
      <div className="flex flex-col gap-5">
        {saved && <Notice tone="success">Venue saved.</Notice>}
        {save.isError && Object.keys(errors).length === 0 && (
          <Notice tone="error">
            {save.error instanceof ApiError
              ? save.error.message
              : 'The venue could not be saved.'}
          </Notice>
        )}
        {text('name', 'Name', 200)}
        {text('address', 'Address', 255)}
        <div className="grid gap-5 sm:grid-cols-2">
          {text('city', 'City', 100)}
          {text('country', 'Country', 100)}
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField
            id="venue-capacity"
            label="Capacity"
            error={errors.capacity}
          >
            {(control) => (
              <Input
                {...control}
                inputMode="numeric"
                value={values.capacity}
                onChange={(e) =>
                  setValues({ ...values, capacity: e.target.value })
                }
              />
            )}
          </FormField>
          <FormField
            id="venue-shape"
            label="Layout"
            hint="Shapes the seat map buyers see."
            error={errors.layout_shape}
          >
            {(control) => (
              <NativeSelect
                {...control}
                value={values.layout_shape}
                onChange={(e) =>
                  setValues({ ...values, layout_shape: e.target.value })
                }
              >
                {SHAPES.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            )}
          </FormField>
        </div>
        <Button
          type="submit"
          variant="ink"
          size="lg"
          className="w-fit"
          disabled={save.isPending}
        >
          {save.isPending ? 'Saving…' : venue ? 'Save venue' : 'Create venue'}
        </Button>
      </div>

      <div className="flex flex-col gap-3">
        <span className="text-sm font-medium">Photo</span>
        <div className="aspect-[4/3] overflow-hidden rounded-lg border border-border bg-muted">
          {shownPhoto ? (
            <img
              src={shownPhoto}
              alt="Venue photo preview"
              className="size-full object-cover"
            />
          ) : (
            <span className="grid size-full place-items-center text-sm text-muted-foreground">
              No photo yet
            </span>
          )}
        </div>
        <label htmlFor="venue-photo" className="sr-only">
          Choose a photo
        </label>
        <input
          id="venue-photo"
          type="file"
          accept={PHOTO_TYPES}
          onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
          className="text-sm file:mr-3 file:h-9 file:rounded-md file:border file:border-hairline-strong file:bg-card file:px-3 file:text-sm file:font-medium hover:file:bg-muted"
        />
        <p className="text-[13px] text-muted-foreground">
          JPEG, PNG or WebP, up to {MAX_PHOTO_MB} MB. A wide shot of the room
          works best.
        </p>
        {errors.photo && <p className="text-sm text-danger">{errors.photo}</p>}
      </div>
    </form>
  )
}

let sectionCounter = 0
const newSection = (): SectionDraft => ({
  key: `s${++sectionCounter}`,
  name: '',
  rows: '',
  seatsPerRow: '',
})

function SeatTemplateEditor({ venue }: { venue: Venue }) {
  const client = useQueryClient()
  const template = useVenueTemplate(venue.id)
  const [sections, setSections] = useState<SectionDraft[]>(() => [newSection()])
  const [submitted, setSubmitted] = useState(false)
  const built = buildTemplate(sections, venue.capacity)

  // Live preview of the draft, drawn with the same layout as the real map
  const previewSeats = useMemo<LayoutSeatInput[]>(() => {
    const seats: LayoutSeatInput[] = []
    for (const section of sections) {
      const rows = parseRowLabels(section.rows)
      const count = Number(section.seatsPerRow)
      if (
        !section.name.trim() ||
        !rows ||
        !Number.isInteger(count) ||
        count < 1 ||
        count > 500
      )
        continue
      for (const row of rows) {
        for (let seat = 1; seat <= count; seat += 1) {
          seats.push({
            id: `${section.key}-${row}-${seat}`,
            section: section.name.trim(),
            row_label: row,
            seat_number: seat,
          })
        }
      }
    }
    return seats.length <= 2000 ? seats : []
  }, [sections])

  const create = useMutation({
    mutationFn: () =>
      apiFetch(`/venues/${venue.id}/seats/`, {
        method: 'POST',
        body: built.payload,
      }),
    onSuccess: () =>
      void client.invalidateQueries({
        queryKey: ['venues', 'template', venue.id],
      }),
  })

  if (template.isPending)
    return (
      <div
        aria-busy="true"
        className="h-64 animate-pulse rounded-lg bg-muted"
      />
    )
  if (template.isError)
    return <Notice tone="error">{template.error.message}</Notice>

  if (template.data.length > 0) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          {template.data.length.toLocaleString()} seats. The seat map can't be
          replaced once events have sold seats from it.
        </p>
        <VenueMapPreview seats={template.data} shape={venue.layout_shape} />
      </div>
    )
  }

  const update = (key: string, changes: Partial<SectionDraft>) =>
    setSections((current) =>
      current.map((section) =>
        section.key === key ? { ...section, ...changes } : section,
      ),
    )

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <form
        noValidate
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault()
          setSubmitted(true)
          if (built.payload) create.mutate()
        }}
      >
        <p className="text-sm text-muted-foreground">
          Describe each section's rows. Write rows as a range (A-H, 1-12) or a
          list (AA, BB, CC).
        </p>
        {sections.map((section, index) => (
          <fieldset
            key={section.key}
            className="grid gap-3 rounded-lg border border-border bg-card p-4 sm:grid-cols-[1fr_8rem_7rem_auto]"
          >
            <legend className="sr-only">Section {index + 1}</legend>
            <FormField
              id={`${section.key}-name`}
              label="Section"
              error={
                submitted ? built.errors[`${section.key}-name`] : undefined
              }
            >
              {(control) => (
                <Input
                  {...control}
                  maxLength={50}
                  value={section.name}
                  onChange={(e) =>
                    update(section.key, { name: e.target.value })
                  }
                />
              )}
            </FormField>
            <FormField
              id={`${section.key}-rows`}
              label="Rows"
              error={
                submitted ? built.errors[`${section.key}-rows`] : undefined
              }
            >
              {(control) => (
                <Input
                  {...control}
                  placeholder="A-H"
                  value={section.rows}
                  onChange={(e) =>
                    update(section.key, { rows: e.target.value })
                  }
                />
              )}
            </FormField>
            <FormField
              id={`${section.key}-seats`}
              label="Seats per row"
              error={
                submitted ? built.errors[`${section.key}-seats`] : undefined
              }
            >
              {(control) => (
                <Input
                  {...control}
                  inputMode="numeric"
                  value={section.seatsPerRow}
                  onChange={(e) =>
                    update(section.key, { seatsPerRow: e.target.value })
                  }
                />
              )}
            </FormField>
            <Button
              variant="ghost"
              size="sm"
              className="self-end sm:mb-1.5"
              disabled={sections.length === 1}
              onClick={() =>
                setSections((current) =>
                  current.filter((s) => s.key !== section.key),
                )
              }
            >
              Remove
            </Button>
          </fieldset>
        ))}
        <Button
          variant="outline"
          size="sm"
          className="w-fit"
          onClick={() => setSections((current) => [...current, newSection()])}
        >
          Add section
        </Button>

        <p className="tabular text-sm">
          {built.total.toLocaleString()} of {venue.capacity.toLocaleString()}{' '}
          seats
        </p>
        {submitted && (built.errors.total || built.errors.sections) && (
          <Notice tone="error">
            {built.errors.total ?? built.errors.sections}
          </Notice>
        )}
        {create.isError && (
          <Notice tone="error">
            {create.error instanceof ApiError
              ? create.error.message
              : 'The seat map could not be saved.'}
          </Notice>
        )}
        <Button
          type="submit"
          variant="ink"
          className="w-fit"
          disabled={create.isPending}
        >
          {create.isPending ? 'Creating seats…' : 'Create seat map'}
        </Button>
      </form>

      <div className="flex flex-col gap-2">
        <span className="text-sm font-medium">Preview</span>
        {previewSeats.length > 0 ? (
          <VenueMapPreview
            seats={previewSeats}
            shape={venue.layout_shape}
            showTable={false}
          />
        ) : (
          <div className="grid aspect-[4/3] place-items-center rounded-lg border border-dashed border-hairline-strong text-sm text-muted-foreground">
            The map appears as you add sections.
          </div>
        )}
      </div>
    </div>
  )
}

export function AdminVenuePage() {
  const { id } = useParams()
  const isNew = id === undefined
  const venues = useVenues()
  const venue = !isNew && isUuid(id) ? venues.data?.byId.get(id) : undefined
  usePageTitle(isNew ? 'Add venue' : venue?.name)

  if (!isNew && venues.isPending) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading venue"
        className="h-96 animate-pulse rounded-lg bg-muted"
      />
    )
  }
  if (!isNew && !venue) {
    return (
      <Notice tone="error">
        This venue could not be found.{' '}
        <Link to="/admin/venues" className="font-medium underline">
          Back to venues
        </Link>
      </Notice>
    )
  }

  return (
    <div className="flex flex-col gap-10">
      <PageHeader
        size="md"
        title={venue ? venue.name : 'Add venue'}
        description={venue ? `${venue.city}, ${venue.country}` : undefined}
      />
      {/* Keyed by id, not updated_at: a save must not remount the form and drop its "saved" notice */}
      <DetailsForm key={venue?.id ?? 'new'} venue={venue} />
      {venue && (
        <section className="flex flex-col gap-4 border-t border-border pt-8">
          <h2 className="text-lg font-semibold tracking-tight">Seat map</h2>
          <SeatTemplateEditor venue={venue} />
        </section>
      )}
    </div>
  )
}
