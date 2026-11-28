import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { useEffect } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, type RequestOptions } from '@/lib/api-client'
import { RegisterPage } from './RegisterPage'

vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  apiFetch: vi.fn(),
}))

// The human check passes at once
vi.mock('../components/Turnstile', () => ({
  Turnstile: ({ onToken }: { onToken: (token: string) => void }) => {
    useEffect(() => onToken('captcha'), [onToken])
    return null
  },
}))

const NUMBERS = [
  { number: '1111222233334444', token: 'token-1' },
  { number: '5555666677778888', token: 'token-2' },
]

function serve(register: (body: unknown) => unknown = () => ({ email: 'x' })) {
  let issued = 0
  vi.mocked(apiFetch).mockImplementation(
    async (path, options: RequestOptions = {}) => {
      if (path === '/payout-account-numbers/') return NUMBERS[issued++]
      if (path === '/auth/register/') {
        const answer = register(options.body)
        if (answer instanceof Error) throw answer
        return answer
      }
      return undefined
    },
  )
  render(
    <MemoryRouter initialEntries={['/register?role=organizer']}>
      <RegisterPage />
    </MemoryRouter>,
  )
}

function numberRequests() {
  return vi
    .mocked(apiFetch)
    .mock.calls.filter(([path]) => path === '/payout-account-numbers/').length
}

function fillIn() {
  const type = (label: string, value: string) =>
    fireEvent.change(screen.getByLabelText(label), { target: { value } })
  type('First name', 'Sana')
  type('Last name', 'Malik')
  type('Email', 'sana@example.com')
  type('Password', 'a-genuinely-strong-pass-1')
  type('Gender', 'female')
  type('Paid to', 'wallet')
  type('Wallet provider', 'JazzCash')
  type('Account holder', 'Sana Malik')
}

describe('RegisterPage payout details', () => {
  afterEach(() => vi.mocked(apiFetch).mockReset())

  it('shows one locked number, kept when the role is switched back and forth', async () => {
    serve()
    const number = await screen.findByDisplayValue('1111 2222 3333 4444')
    expect(number).toHaveAttribute('readonly')

    fireEvent.click(screen.getByLabelText(/Attendee/))
    fireEvent.click(screen.getByLabelText(/Organizer/))

    expect(
      await screen.findByDisplayValue('1111 2222 3333 4444'),
    ).toBeInTheDocument()
    expect(numberRequests()).toBe(1)
  })

  it('sends the token, never the number', async () => {
    const sent: unknown[] = []
    serve((body) => {
      sent.push(body)
      return { email: 'sana@example.com' }
    })
    await screen.findByDisplayValue('1111 2222 3333 4444')
    fillIn()

    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    await screen.findByText('Check your email')
    expect(sent).toHaveLength(1)
    expect(JSON.stringify(sent[0])).not.toContain('1111222233334444')
    expect(sent[0]).toMatchObject({
      payout_account: {
        method: 'wallet',
        provider: 'JazzCash',
        holder_name: 'Sana Malik',
        number_token: 'token-1',
      },
    })
  })

  it('gets a fresh number when the server refuses the token', async () => {
    serve(
      () =>
        new ApiError(409, 'Taken', {
          payout_account: {
            number_token: ['This account number is already in use.'],
          },
        }),
    )
    await screen.findByDisplayValue('1111 2222 3333 4444')
    fillIn()

    fireEvent.click(screen.getByRole('button', { name: 'Create account' }))

    expect(
      await screen.findByDisplayValue('5555 6666 7777 8888'),
    ).toBeInTheDocument()
    await waitFor(() =>
      expect(
        screen.getAllByText(/already in use. We’ve given you a new one./)
          .length,
      ).toBeGreaterThan(0),
    )
  })
})
