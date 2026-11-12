import { useRef, useState, type FormEvent } from 'react'
import { useParams } from 'react-router-dom'
import { FormField } from '@/components/FormField'
import { LoadingBlock } from '@/components/LoadingBlock'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { EventNotFound } from '@/features/events/components/EventNotFound'
import { useEvent } from '@/features/events/hooks'
import { ApiError, errorMessage } from '@/lib/api-client'
import { isUuid } from '@/lib/ids'
import { usePageTitle } from '@/lib/use-page-title'
import { useCheckIn } from '../api'

// The code is shown too, so two refusals in a row still look different
type Result = { code: string } & (
  | { admitted: true; seat: string; name: string }
  | { admitted: false; reason: string }
)

// Staff type the code under the QR, or use a USB or Bluetooth scanner, which
// types it and presses Enter. The server decides; this page only reports.
export function DoorPage() {
  const { id } = useParams()
  const event = useEvent(id)
  usePageTitle(event.data ? `Door: ${event.data.title}` : 'Door')
  const checkIn = useCheckIn(id ?? '')
  const [code, setCode] = useState('')
  const [result, setResult] = useState<Result | null>(null)
  const input = useRef<HTMLInputElement>(null)

  if (
    !isUuid(id) ||
    (event.error instanceof ApiError && event.error.status === 404)
  ) {
    return <EventNotFound />
  }
  if (event.isPending) {
    return <LoadingBlock label="Loading event" className="h-64" />
  }
  if (event.isError) {
    return <Notice tone="error">{event.error.message}</Notice>
  }

  function submit(e: FormEvent) {
    e.preventDefault()
    const scanned = code.trim()
    if (!scanned || checkIn.isPending) return
    checkIn.mutate(scanned, {
      onSuccess: (ticket) =>
        setResult({
          code: scanned,
          admitted: true,
          seat: `${ticket.section}, row ${ticket.row_label}, seat ${ticket.seat_number}`,
          name: ticket.attendee_name,
        }),
      onError: (caught) =>
        setResult({
          code: scanned,
          admitted: false,
          reason: errorMessage(caught, 'The ticket could not be checked.'),
        }),
      // Ready for the next person straight away
      onSettled: () => {
        setCode('')
        input.current?.focus()
      },
    })
  }

  return (
    <div className="flex max-w-xl flex-col gap-8">
      <PageHeader
        size="md"
        title="Door"
        description={`Check tickets in for ${event.data.title}. Each ticket gets in once.`}
      />

      <form
        onSubmit={submit}
        className="flex flex-col gap-3 sm:flex-row sm:items-end"
      >
        <div className="flex-1">
          <FormField id="door-code" label="Ticket code">
            {(control) => (
              <Input
                {...control}
                ref={input}
                value={code}
                onChange={(e) => setCode(e.target.value)}
                maxLength={32}
                autoFocus
                autoComplete="off"
                autoCapitalize="off"
                spellCheck={false}
              />
            )}
          </FormField>
        </div>
        <Button type="submit" variant="ink" disabled={checkIn.isPending}>
          {checkIn.isPending ? 'Checking…' : 'Check in'}
        </Button>
      </form>

      {result &&
        (result.admitted ? (
          <Notice tone="success">
            <strong className="block text-lg">Admitted: {result.code}</strong>
            {result.seat}
            {result.name && ` · ${result.name}`}
          </Notice>
        ) : (
          <Notice tone="error">
            <strong className="block text-lg">
              Not admitted: {result.code}
            </strong>
            {result.reason}
          </Notice>
        ))}
    </div>
  )
}
