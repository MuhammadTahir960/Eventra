import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch } from '@/lib/api-client'
import { DeleteAccountSection } from './DeleteAccountSection'

vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiFetch: vi.fn(),
}))

async function holdToDelete(password: string) {
  render(
    <MemoryRouter>
      <DeleteAccountSection />
    </MemoryRouter>,
  )
  fireEvent.click(screen.getByRole('button', { name: 'Delete account' }))
  fireEvent.change(screen.getByLabelText('Your password'), {
    target: { value: password },
  })
  const hold = screen.getAllByRole('button', { name: /Hold to delete/ })[0]
  fireEvent.keyDown(hold, { key: ' ' })
  await act(async () => {
    vi.advanceTimersByTime(1600)
  })
}

describe('DeleteAccountSection', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => {
    vi.useRealTimers()
    vi.mocked(apiFetch).mockReset()
  })

  it('lists every reason the server gives for refusing', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new ApiError(409, "Your account can't be deleted yet.", {
        detail: "Your account can't be deleted yet.",
        reasons: ['You have tickets.', 'A refund is in progress.'],
      }),
    )
    await holdToDelete('secret-pass')
    expect(screen.getByText('You have tickets.')).toBeInTheDocument()
    expect(screen.getByText('A refund is in progress.')).toBeInTheDocument()
  })

  it('shows a wrong password under the field', async () => {
    vi.mocked(apiFetch).mockRejectedValue(
      new ApiError(400, "That password isn't right.", {
        password: ["That password isn't right."],
      }),
    )
    await holdToDelete('wrong')
    expect(screen.getByText("That password isn't right.")).toBeInTheDocument()
  })

  it('asks for the password before calling the server', async () => {
    await holdToDelete('')
    expect(screen.getByText('Enter your password.')).toBeInTheDocument()
    expect(apiFetch).not.toHaveBeenCalled()
  })
})
