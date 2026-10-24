import { useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, type FormEvent } from 'react'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { EmptyState } from '@/components/EmptyState'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { StatusBadge } from '@/components/StatusBadge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { ApiError, apiFetch } from '@/lib/api-client'
import { formatDateTime } from '@/lib/format'
import {
  VENUE_REQUEST_STATUS,
  useCreateVenueRequest,
  useVenueRequests,
  type VenueRequest,
} from '../api'
import { usePageTitle } from '@/lib/use-page-title'
import { toast } from 'sonner'

function RequestForm() {
  const create = useCreateVenueRequest()
  const [values, setValues] = useState({ venue_name: '', city: '', notes: '' })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [sent, setSent] = useState(false)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const clientErrors: Record<string, string> = {}
    if (values.venue_name.trim().length < 2)
      clientErrors.venue_name = 'Enter the venue name.'
    if (!values.city.trim()) clientErrors.city = 'Enter the city.'
    setErrors(clientErrors)
    setSent(false)
    if (Object.keys(clientErrors).length > 0) return

    create.mutate(
      {
        venue_name: values.venue_name.trim(),
        city: values.city.trim(),
        notes: values.notes.trim(),
      },
      {
        onSuccess: () => {
          setValues({ venue_name: '', city: '', notes: '' })
          setSent(true)
        },
        onError: (caught) => {
          if (caught instanceof ApiError) {
            setErrors(
              Object.fromEntries(
                Object.entries(caught.fieldErrors).map(([k, m]) => [k, m[0]]),
              ),
            )
          }
        },
      },
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="flex flex-col gap-5 rounded-lg border border-border bg-card p-5 sm:p-6"
    >
      <div>
        <h2 className="text-lg font-semibold tracking-tight">
          Request a venue
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Can't find your venue when creating an event? An admin adds it with
          its seat map.
        </p>
      </div>
      {sent && (
        <Notice tone="success">
          Request sent. You'll see its status below.
        </Notice>
      )}
      {create.isError &&
        !(
          create.error instanceof ApiError &&
          Object.keys(create.error.fieldErrors).length
        ) && (
          <Notice tone="error">
            {create.error instanceof ApiError
              ? create.error.message
              : 'The request could not be sent.'}
          </Notice>
        )}
      <div className="grid gap-5 sm:grid-cols-2">
        <FormField id="vr-name" label="Venue name" error={errors.venue_name}>
          {(control) => (
            <Input
              {...control}
              maxLength={200}
              value={values.venue_name}
              onChange={(e) =>
                setValues({ ...values, venue_name: e.target.value })
              }
            />
          )}
        </FormField>
        <FormField id="vr-city" label="City" error={errors.city}>
          {(control) => (
            <Input
              {...control}
              maxLength={100}
              value={values.city}
              onChange={(e) => setValues({ ...values, city: e.target.value })}
            />
          )}
        </FormField>
      </div>
      <FormField
        id="vr-notes"
        label="Notes"
        hint="Address, capacity, how the seating is laid out."
        error={errors.notes}
      >
        {(control) => (
          <Textarea
            {...control}
            rows={4}
            maxLength={2000}
            value={values.notes}
            onChange={(e) => setValues({ ...values, notes: e.target.value })}
          />
        )}
      </FormField>
      <Button
        type="submit"
        variant="ink"
        className="w-fit"
        disabled={create.isPending}
      >
        {create.isPending ? 'Sending…' : 'Send request'}
      </Button>
    </form>
  )
}

// Admin decision on a pending request. Fulfil means the admin has created the
// venue; reject needs a note explaining why.
function ReviewActions({ request }: { request: VenueRequest }) {
  const client = useQueryClient()
  const [mode, setMode] = useState<'fulfil' | 'reject' | null>(null)
  const [notes, setNotes] = useState('')
  const review = useMutation({
    mutationFn: (action: 'fulfil' | 'reject') =>
      apiFetch<VenueRequest>(`/venues/requests/${request.id}/${action}/`, {
        method: 'POST',
        body: action === 'reject' ? { admin_notes: notes.trim() } : undefined,
      }),
    onSuccess: (_, action) => {
      toast.success(
        action === 'reject' ? 'Request declined' : 'Request marked as added',
      )
      setMode(null)
      setNotes('')
      void client.invalidateQueries({ queryKey: ['venue-requests'] })
    },
  })

  const dialog = (action: 'fulfil' | 'reject') => (
    <ConfirmDialog
      open={mode === action}
      onOpenChange={(open) => {
        setMode(open ? action : null)
        if (!open) review.reset()
      }}
      trigger={
        <Button
          variant={action === 'reject' ? 'destructive' : 'outline'}
          size="sm"
        >
          {action === 'reject' ? 'Decline' : 'Mark added'}
        </Button>
      }
      title={action === 'reject' ? 'Decline this request?' : 'Mark as added?'}
      description={
        action === 'reject'
          ? `Tell the organizer why "${request.venue_name}" won't be added.`
          : `Confirm that "${request.venue_name}" now exists as a venue with its seat map.`
      }
      confirmLabel={action === 'reject' ? 'Decline request' : 'Mark added'}
      destructive={action === 'reject'}
      pending={review.isPending}
      onConfirm={() => review.mutate(action)}
    >
      {/* Only a decline takes a note; marking it added has nothing to send */}
      {action === 'reject' && (
        <FormField id={`notes-${request.id}`} label="Reason">
          {(control) => (
            <Textarea
              {...control}
              rows={3}
              maxLength={2000}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          )}
        </FormField>
      )}
      {review.isError && (
        <Notice tone="error" className="mt-3">
          {review.error instanceof ApiError
            ? review.error.message
            : 'The request could not be updated.'}
        </Notice>
      )}
    </ConfirmDialog>
  )

  return (
    <div className="flex justify-end gap-2">
      {dialog('fulfil')}
      {dialog('reject')}
    </div>
  )
}

export function VenueRequestsPage({ scope }: { scope: 'organizer' | 'admin' }) {
  usePageTitle('Venue requests')
  const requests = useVenueRequests()
  // Oldest first from the API; newest first reads better here
  const list = [...(requests.data?.results ?? [])].reverse()

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Venue requests"
        description={
          scope === 'admin'
            ? 'Requests from organizers for venues that are missing.'
            : undefined
        }
      />

      {scope === 'organizer' && <RequestForm />}

      {requests.isError ? (
        <Notice tone="error">{requests.error.message}</Notice>
      ) : requests.isPending ? (
        <div
          aria-busy="true"
          aria-label="Loading requests"
          className="h-40 animate-pulse rounded-lg bg-muted"
        />
      ) : list.length === 0 ? (
        <EmptyState
          title="No requests"
          body={
            scope === 'admin'
              ? 'Nothing waiting for review.'
              : "Requests you send appear here with the admin's answer."
          }
        />
      ) : (
        <div className="relative overflow-x-auto rounded-lg border border-border bg-card">
          <table className="data-table">
            <thead>
              <tr>
                <th scope="col">Venue</th>
                <th scope="col">Notes</th>
                <th scope="col">Status</th>
                {scope === 'admin' && (
                  <th scope="col">
                    <span className="sr-only">Actions</span>
                  </th>
                )}
              </tr>
            </thead>
            <tbody>
              {list.map((request) => {
                const status = VENUE_REQUEST_STATUS[request.status]
                return (
                  <tr key={request.id}>
                    <td className="min-w-48">
                      <span className="font-medium">{request.venue_name}</span>
                      <span className="block text-[13px] text-muted-foreground">
                        {request.city}, sent{' '}
                        <span className="tabular">
                          {formatDateTime(request.created_at)}
                        </span>
                      </span>
                    </td>
                    <td className="max-w-80 text-muted-foreground">
                      <span className="line-clamp-2">{request.notes}</span>
                      {request.admin_notes && (
                        <span className="mt-1 block text-[13px] text-foreground">
                          Admin: {request.admin_notes}
                        </span>
                      )}
                    </td>
                    <td>
                      <StatusBadge tone={status.tone}>
                        {status.label}
                      </StatusBadge>
                    </td>
                    {scope === 'admin' && (
                      <td>
                        {request.status === 'pending' && (
                          <ReviewActions request={request} />
                        )}
                      </td>
                    )}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
