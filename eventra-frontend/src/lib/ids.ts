const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

// Route params and query strings are user-controlled, so check their shape
// before sending them to the API.
// ?page= from the URL: a whole number above 1, otherwise the first page
export function pageParam(value: string | null): number {
  const page = Number(value)
  return Number.isInteger(page) && page > 1 ? page : 1
}

export function isUuid(value: string | null | undefined): value is string {
  return typeof value === 'string' && UUID_PATTERN.test(value)
}
