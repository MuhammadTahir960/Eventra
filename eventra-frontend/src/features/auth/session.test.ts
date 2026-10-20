import { beforeEach, describe, expect, it, vi } from 'vitest'
import { authApi } from './api'
import { authStore } from './auth-store'
import { refreshTokens } from './session'

vi.mock('./api', () => ({ authApi: { refresh: vi.fn() } }))

describe('refreshTokens', () => {
  beforeEach(() => authStore.clear())

  it('does not restore tokens when the user signs out mid-refresh', async () => {
    let resolve!: (v: { access: string; refresh: string }) => void
    vi.mocked(authApi.refresh).mockReturnValue(
      new Promise((r) => (resolve = r)) as never,
    )
    authStore.setTokens('old-access', 'old-refresh')

    const pending = refreshTokens()
    authStore.clear()
    resolve({ access: 'new-access', refresh: 'new-refresh' })

    expect(await pending).toBeNull()
    expect(authStore.getState().refreshToken).toBeNull()
  })

  it('stores the rotated tokens when the session is unchanged', async () => {
    vi.mocked(authApi.refresh).mockResolvedValue({
      access: 'new-access',
      refresh: 'new-refresh',
    } as never)
    authStore.setTokens('old-access', 'old-refresh')

    expect(await refreshTokens()).toBe('new-access')
    expect(authStore.getState().refreshToken).toBe('new-refresh')
  })
})
