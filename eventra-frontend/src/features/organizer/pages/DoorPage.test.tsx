import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from '@/lib/api-client'
import { DoorPage } from './DoorPage'

vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiFetch: vi.fn(),
}))

const EVENT_ID = '22222222-2222-4222-8222-222222222222'

function open(checkIn: () => unknown) {
  vi.mocked(apiFetch).mockImplementation(async (path) => {
    if (path === `/events/${EVENT_ID}/`)
      return { id: EVENT_ID, title: 'Harbour Lights', status: 'approved' }
    if (path === `/events/${EVENT_ID}/check-ins/`) return checkIn()
    return { count: 0, next: null, previous: null, results: [] }
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[`/organizer/events/${EVENT_ID}/door`]}>
        <Routes>
          <Route path="/organizer/events/:id/door" element={<DoorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

async function scan(code: string) {
  const input = await screen.findByLabelText('Ticket code')
  fireEvent.change(input, { target: { value: `  ${code} ` } })
  fireEvent.click(screen.getByRole('button', { name: 'Check in' }))
  return input
}

describe('DoorPage', () => {
  afterEach(() => vi.mocked(apiFetch).mockReset())

  it('sends the trimmed code and shows the seat when admitted', async () => {
    open(() => ({
      section: 'Stalls',
      row_label: 'B',
      seat_number: 7,
      attendee_name: 'Ana Ruiz',
    }))
    const input = await scan('K7QM-4XPD-9TRB')

    expect(
      await screen.findByText('Admitted: K7QM-4XPD-9TRB'),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Stalls, row B, seat 7 · Ana Ruiz/),
    ).toBeInTheDocument()
    expect(apiFetch).toHaveBeenCalledWith(`/events/${EVENT_ID}/check-ins/`, {
      method: 'POST',
      body: { code: 'K7QM-4XPD-9TRB' },
    })
    expect(input).toHaveValue('')
  })

  it("shows the server's reason when a ticket is refused", async () => {
    open(() => {
      throw new ApiError(409, 'Ticket already used', {
        detail: 'Ticket already used',
      })
    })
    await scan('HV2N-8CQE-5WRT')

    expect(
      await screen.findByText('Not admitted: HV2N-8CQE-5WRT'),
    ).toBeInTheDocument()
    expect(screen.getByText('Ticket already used')).toBeInTheDocument()
  })
})
