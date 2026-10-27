import { QueryClient } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { authStore, type SessionUser } from '@/features/auth/auth-store'
import { saveCheckoutContext } from '@/features/bookings/api'
import { clearCacheOnUserChange } from './clear-cache-on-user-change'

const user = (id: string): SessionUser => ({
  id,
  email: `${id}@example.com`,
  role: 'attendee',
  first_name: '',
  last_name: '',
  gender: '',
  avatar: null,
})

describe('clearCacheOnUserChange', () => {
  let client: QueryClient
  let stop: () => void

  beforeEach(() => {
    authStore.clear()
    sessionStorage.clear()
    client = new QueryClient()
    stop = clearCacheOnUserChange(client)
  })
  afterEach(() => stop())

  const cachedTicket = () => client.getQueryData(['tickets', 'detail', 't1'])
  const savedContext = () => sessionStorage.getItem('eventra-checkout-b1')

  it('keeps public data cached when a visitor signs in', () => {
    client.setQueryData(['events', 'list'], ['public'])
    authStore.setSession(user('a'), 'access', 'refresh')
    expect(client.getQueryData(['events', 'list'])).toEqual(['public'])
  })

  it('keeps the cache when the same user is updated', () => {
    authStore.setSession(user('a'), 'access', 'refresh')
    client.setQueryData(['tickets', 'detail', 't1'], { ticket_code: 'A-CODE' })
    authStore.setUser({ ...user('a'), first_name: 'Ada' })
    expect(cachedTicket()).toEqual({ ticket_code: 'A-CODE' })
  })

  it('drops the cache and checkout summaries when the user signs out', () => {
    authStore.setSession(user('a'), 'access', 'refresh')
    client.setQueryData(['tickets', 'detail', 't1'], { ticket_code: 'A-CODE' })
    saveCheckoutContext('b1', { eventId: 'e1', eventTitle: 'Gig', seats: [] })

    authStore.clear()

    expect(cachedTicket()).toBeUndefined()
    expect(savedContext()).toBeNull()
  })

  it('drops the cache when another account signs in without a sign-out', () => {
    authStore.setSession(user('a'), 'access', 'refresh')
    client.setQueryData(['tickets', 'detail', 't1'], { ticket_code: 'A-CODE' })

    authStore.setSession(user('b'), 'access-b', 'refresh-b')

    expect(cachedTicket()).toBeUndefined()
  })
})
