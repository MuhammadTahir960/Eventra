import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, type RequestOptions } from '@/lib/api-client'
import type { EventItem } from '@/features/events/types'
import { TrashPage } from './TrashPage'

vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiFetch: vi.fn(),
}))

const EVENT = {
  id: '11111111-1111-4111-8111-111111111111',
  title: 'Old Jazz Night',
  status: 'cancelled',
  event_type: 'general',
  venue: null,
  category: null,
  start_datetime: '2026-10-01T18:00:00Z',
  end_datetime: '2026-10-01T21:00:00Z',
  postponed_from: null,
  is_active: false,
} as unknown as EventItem

function serve(
  respond: (path: string, options: RequestOptions) => unknown = () => undefined,
) {
  vi.mocked(apiFetch).mockImplementation(async (path, options = {}) => {
    const answer = respond(path, options)
    if (answer instanceof Error) throw answer
    if (answer !== undefined) return answer
    if (path === '/events/' && options.query?.is_active === false)
      return { count: 1, next: null, previous: null, results: [EVENT] }
    return { count: 0, next: null, previous: null, results: [] }
  })
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <TrashPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('TrashPage', () => {
  afterEach(() => vi.mocked(apiFetch).mockReset())

  it('lists deleted events without linking to their missing public page', async () => {
    serve()
    expect(await screen.findByText('Old Jazz Night')).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'Old Jazz Night' }),
    ).not.toBeInTheDocument()
    expect(apiFetch).toHaveBeenCalledWith(
      '/events/',
      expect.objectContaining({
        query: { include_inactive: true, is_active: false, page: 1 },
      }),
    )
  })

  it('restores an event', async () => {
    serve()
    fireEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(`/events/${EVENT.id}/restore/`, {
        method: 'POST',
      }),
    )
  })

  it("shows the server's reason when an event can't be deleted forever", async () => {
    serve((_path, options) =>
      options.method === 'DELETE'
        ? new ApiError(409, 'Cannot permanently delete: still referenced.', {
            detail: 'Cannot permanently delete: still referenced.',
          })
        : undefined,
    )
    fireEvent.click(
      await screen.findByRole('button', { name: 'Delete forever' }),
    )
    const confirm = screen.getAllByRole('button', { name: 'Delete forever' })
    fireEvent.click(confirm[confirm.length - 1])
    expect(
      await screen.findByText('Cannot permanently delete: still referenced.'),
    ).toBeInTheDocument()
    expect(apiFetch).toHaveBeenCalledWith(`/events/${EVENT.id}/`, {
      method: 'DELETE',
      query: { hard: true },
    })
  })
})
