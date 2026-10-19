import { API_BASE_URL } from './config'

// Thrown for every failed request (HTTP error or network failure)
export class ApiError extends Error {
  // 0 means the request never got a response (offline, CORS, server down)
  status: number
  // Parsed JSON body when there was one (DRF error shapes)
  data: unknown

  constructor(status: number, message: string, data?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }

  // DRF validation errors look like { email: ["..."], password: ["..."] }
  get fieldErrors(): Record<string, string[]> {
    const result: Record<string, string[]> = {}
    if (
      this.data &&
      typeof this.data === 'object' &&
      !Array.isArray(this.data)
    ) {
      for (const [key, value] of Object.entries(this.data)) {
        if (key === 'detail') continue
        if (Array.isArray(value)) result[key] = value.map(String)
        else if (typeof value === 'string') result[key] = [value]
      }
    }
    return result
  }
}

// Turn any DRF error body into one readable sentence
function messageFromBody(status: number, body: unknown): string {
  if (body && typeof body === 'object' && !Array.isArray(body)) {
    const record = body as Record<string, unknown>
    if (typeof record.detail === 'string') return record.detail
    for (const value of Object.values(record)) {
      if (Array.isArray(value) && value.length > 0) return String(value[0])
      if (typeof value === 'string') return value
    }
  }
  if (status === 429) return 'Too many requests. Please wait and try again.'
  return `Request failed (${status}).`
}

// The auth feature registers these at startup. Keeping them behind an
// interface means this file never imports a feature folder.
interface AuthHandlers {
  getAccessToken: () => string | null
  // Resolves to a fresh access token, or null if the session is gone
  refreshAccessToken: () => Promise<string | null>
}

let authHandlers: AuthHandlers | null = null

export function configureApiAuth(handlers: AuthHandlers) {
  authHandlers = handlers
}

type QueryValue = string | number | boolean | null | undefined

export interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  // Plain objects are sent as JSON; FormData is sent as multipart
  body?: unknown
  query?: Record<string, QueryValue>
  // false for public endpoints (login, register, refresh)
  auth?: boolean
  signal?: AbortSignal
}

function buildUrl(path: string, query?: Record<string, QueryValue>): string {
  const url = new URL(`${API_BASE_URL}${path}`)
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      // Skip empty filters so they don't become "?city="
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.set(key, String(value))
      }
    }
  }
  return url.toString()
}

async function send(
  path: string,
  options: RequestOptions,
  hasRetried: boolean,
): Promise<Response> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  const useAuth = options.auth !== false

  const token = useAuth ? authHandlers?.getAccessToken() : null
  if (token) headers.Authorization = `Bearer ${token}`

  let body: BodyInit | undefined
  if (options.body instanceof FormData) {
    // The browser sets the multipart boundary itself
    body = options.body
  } else if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(options.body)
  }

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body,
      signal: options.signal,
    })
  } catch (error) {
    // A cancelled request is not an error worth surfacing
    if (error instanceof DOMException && error.name === 'AbortError')
      throw error
    throw new ApiError(0, 'Could not reach the server. Check your connection.')
  }

  // Expired access token: refresh once (shared across callers) and retry
  if (response.status === 401 && useAuth && !hasRetried && authHandlers) {
    const fresh = await authHandlers.refreshAccessToken()
    if (fresh) return send(path, options, true)
  }
  return response
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const response = await send(path, options, false)

  // 204/205 have no body (logout returns 205)
  const hasBody = response.status !== 204 && response.status !== 205
  let data: unknown = undefined
  if (hasBody) {
    // A proxy error page isn't JSON; fall back to a generic message below
    data = await response.json().catch(() => undefined)
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      messageFromBody(response.status, data),
      data,
    )
  }
  return data as T
}

// For file downloads (ticket PDFs): same auth and refresh as apiFetch, but
// the body comes back as a Blob instead of being parsed as JSON.
export async function apiDownload(
  path: string,
  options: Omit<RequestOptions, 'body' | 'method'> = {},
): Promise<Blob> {
  const response = await send(path, options, false)
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => undefined)
    throw new ApiError(
      response.status,
      messageFromBody(response.status, data),
      data,
    )
  }
  return response.blob()
}
