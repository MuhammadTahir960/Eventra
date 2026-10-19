import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, apiFetch, configureApiAuth } from './api-client'

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })

describe('apiFetch', () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    configureApiAuth({
      getAccessToken: () => 'old-token',
      refreshAccessToken: async () => null,
    })
  })

  afterEach(() => {
    fetchMock.mockReset()
    vi.unstubAllGlobals()
  })

  it('sends the access token and parses JSON', async () => {
    fetchMock.mockResolvedValueOnce(json({ ok: true }))
    const data = await apiFetch<{ ok: boolean }>('/auth/me/')

    expect(data).toEqual({ ok: true })
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<
      string,
      string
    >
    expect(headers.Authorization).toBe('Bearer old-token')
  })

  it('skips the token for public endpoints', async () => {
    fetchMock.mockResolvedValueOnce(json({}))
    await apiFetch('/auth/login/', { method: 'POST', body: {}, auth: false })

    const headers = fetchMock.mock.calls[0][1]?.headers as Record<
      string,
      string
    >
    expect(headers.Authorization).toBeUndefined()
  })

  it('refreshes once on 401 and retries with the new token', async () => {
    configureApiAuth({
      getAccessToken: () => 'old-token',
      refreshAccessToken: async () => 'new-token',
    })
    fetchMock
      .mockResolvedValueOnce(json({ detail: 'expired' }, 401))
      .mockResolvedValueOnce(json({ ok: true }))

    const data = await apiFetch<{ ok: boolean }>('/auth/me/')

    expect(data.ok).toBe(true)
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('gives up with the 401 if the refresh fails', async () => {
    fetchMock.mockResolvedValueOnce(json({ detail: 'expired' }, 401))

    await expect(apiFetch('/auth/me/')).rejects.toMatchObject({ status: 401 })
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('exposes DRF field errors and a readable message', async () => {
    fetchMock.mockResolvedValueOnce(
      json({ email: ['A user with that email already exists.'] }, 400),
    )

    const error = await apiFetch('/auth/register/', {
      method: 'POST',
      body: {},
      auth: false,
    }).catch((caught: unknown) => caught)

    expect(error).toBeInstanceOf(ApiError)
    const apiError = error as ApiError
    expect(apiError.status).toBe(400)
    expect(apiError.message).toBe('A user with that email already exists.')
    expect(apiError.fieldErrors.email).toEqual([
      'A user with that email already exists.',
    ])
  })

  it('treats 205 (logout) as an empty success', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 205 }))
    await expect(
      apiFetch('/auth/logout/', { method: 'POST', body: { refresh: 'x' } }),
    ).resolves.toBeUndefined()
  })

  it('reports an unreachable server as status 0', async () => {
    fetchMock.mockRejectedValueOnce(new TypeError('Failed to fetch'))
    await expect(apiFetch('/events/')).rejects.toMatchObject({ status: 0 })
  })
})
