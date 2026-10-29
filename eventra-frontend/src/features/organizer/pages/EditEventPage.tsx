import { useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { Textarea } from '@/components/ui/textarea'
import { useCategories } from '@/features/catalog/hooks'
import { useEvent } from '@/features/events/hooks'
import { EVENT_STATUS } from '@/features/events/status'
import type { EventItem } from '@/features/events/types'
import { ApiError } from '@/lib/api-client'
import { toLocalInput } from '@/lib/format'
import { isUuid } from '@/lib/ids'
import { useUpdateEvent, type EventPatch } from '../api'
import { usePageTitle } from '@/lib/use-page-title'

interface Values {
  title: string
  description: string
  category: string
  start: string
  end: string
}

function initialValues(event: EventItem): Values {
  return {
    title: event.title,
    description: event.description,
    category: event.category ?? '',
    start: toLocalInput(event.start_datetime),
    end: toLocalInput(event.end_datetime),
  }
}

// Only the fields that really changed are sent, so an untouched date never
// sends the event back for approval
function diff(event: EventItem, values: Values): EventPatch {
  const patch: EventPatch = {}
  if (values.title.trim() !== event.title) patch.title = values.title.trim()
  if (values.description.trim() !== event.description)
    patch.description = values.description.trim()
  if (values.category !== (event.category ?? ''))
    patch.category = values.category
  if (values.start !== toLocalInput(event.start_datetime))
    patch.start_datetime = new Date(values.start).toISOString()
  if (values.end !== toLocalInput(event.end_datetime))
    patch.end_datetime = new Date(values.end).toISOString()
  return patch
}

function EditForm({ event }: { event: EventItem }) {
  const categories = useCategories()
  const update = useUpdateEvent(event.id)
  const [values, setValues] = useState(() => initialValues(event))
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [notice, setNotice] = useState<{
    tone: 'success' | 'error'
    text: string
  } | null>(null)

  const patch = diff(event, values)
  const changed = Object.keys(patch).length > 0
  const needsReview =
    event.status !== 'pending_approval' &&
    ('category' in patch ||
      'start_datetime' in patch ||
      'end_datetime' in patch)

  function set<K extends keyof Values>(key: K, value: Values[K]) {
    setValues((current) => ({ ...current, [key]: value }))
  }

  function handleSubmit(submit: FormEvent) {
    submit.preventDefault()
    const clientErrors: Record<string, string> = {}
    if (!values.title.trim()) clientErrors.title = 'Enter a title.'
    if (!values.start) clientErrors.start_datetime = 'Choose a start time.'
    if (!values.end) clientErrors.end_datetime = 'Choose an end time.'
    if (
      values.start &&
      values.end &&
      new Date(values.end) <= new Date(values.start)
    )
      clientErrors.end_datetime = 'The end must be after the start.'
    setErrors(clientErrors)
    setNotice(null)
    if (Object.keys(clientErrors).length > 0) return

    update.mutate(patch, {
      onSuccess: (saved) => {
        setValues(initialValues(saved))
        setNotice({
          tone: 'success',
          text:
            saved.status === 'pending_approval' &&
            event.status !== 'pending_approval'
              ? 'Saved. The event is back with an admin for approval.'
              : 'Changes saved.',
        })
      },
      onError: (caught) => {
        if (caught instanceof ApiError) {
          const fields = Object.fromEntries(
            Object.entries(caught.fieldErrors).map(([key, messages]) => [
              key,
              messages[0],
            ]),
          )
          setErrors(fields)
          if (Object.keys(fields).length === 0)
            setNotice({ tone: 'error', text: caught.message })
        } else {
          setNotice({ tone: 'error', text: 'Your changes could not be saved.' })
        }
      },
    })
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="flex max-w-2xl flex-col gap-5"
    >
      {notice && <Notice tone={notice.tone}>{notice.text}</Notice>}

      <FormField id="edit-title" label="Title" error={errors.title}>
        {(control) => (
          <Input
            {...control}
            value={values.title}
            maxLength={100}
            onChange={(e) => set('title', e.target.value)}
          />
        )}
      </FormField>

      <FormField id="edit-category" label="Category" error={errors.category}>
        {(control) => (
          <NativeSelect
            {...control}
            value={values.category}
            onChange={(e) => set('category', e.target.value)}
          >
            {(categories.data?.list ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </NativeSelect>
        )}
      </FormField>

      <div className="grid gap-5 sm:grid-cols-2">
        <FormField id="edit-start" label="Starts" error={errors.start_datetime}>
          {(control) => (
            <Input
              {...control}
              type="datetime-local"
              value={values.start}
              onChange={(e) => set('start', e.target.value)}
            />
          )}
        </FormField>
        <FormField id="edit-end" label="Ends" error={errors.end_datetime}>
          {(control) => (
            <Input
              {...control}
              type="datetime-local"
              value={values.end}
              onChange={(e) => set('end', e.target.value)}
            />
          )}
        </FormField>
      </div>

      <FormField
        id="edit-description"
        label="Description"
        error={errors.description}
      >
        {(control) => (
          <Textarea
            {...control}
            rows={6}
            maxLength={5000}
            value={values.description}
            onChange={(e) => set('description', e.target.value)}
          />
        )}
      </FormField>

      {needsReview && (
        <Notice tone="warning">
          Changing the category or dates sends the event back to an admin for
          approval. It comes off sale until it's approved again.
        </Notice>
      )}

      <div className="flex flex-wrap gap-3">
        <Button
          type="submit"
          variant="ink"
          size="lg"
          disabled={!changed || update.isPending}
        >
          {update.isPending ? 'Saving…' : 'Save changes'}
        </Button>
        <ButtonLink variant="ghost" size="lg" to="/organizer/events">
          Back to my events
        </ButtonLink>
      </div>
      <p className="text-[13px] text-muted-foreground">
        The venue, seat map and ticket prices are fixed once seats are on sale.
      </p>
    </form>
  )
}

export function EditEventPage() {
  const { id } = useParams()
  const event = useEvent(id)
  usePageTitle(event.data ? `Edit: ${event.data.title}` : 'Edit event')

  if (!isUuid(id) || event.isError) {
    return (
      <Notice tone="error">
        {event.error instanceof ApiError
          ? event.error.message
          : 'This event could not be found.'}
      </Notice>
    )
  }
  if (event.isPending) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading event"
        className="h-96 animate-pulse rounded-lg bg-muted"
      />
    )
  }

  const item = event.data
  const status = EVENT_STATUS[item.status]
  const terminal = item.status === 'cancelled' || item.status === 'completed'

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Edit event"
        description={item.title}
        actions={<StatusBadge tone={status.tone}>{status.label}</StatusBadge>}
      />
      {item.status === 'rejected' && item.rejection_reason && (
        <Notice tone="error">
          <strong className="font-semibold">Why it was rejected:</strong>{' '}
          {item.rejection_reason}
        </Notice>
      )}
      {terminal ? (
        <Notice>
          A {status.label.toLowerCase()} event can no longer be edited.
        </Notice>
      ) : (
        // Keyed by id, not updated_at: a save must not remount the form and drop its notice
        <EditForm key={item.id} event={item} />
      )}
    </div>
  )
}
