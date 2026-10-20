import { apiFetch, type RequestOptions } from './api-client'

// DRF's PageNumberPagination envelope (page size 50 on this backend)
export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

// Safety cap so a bug can never loop forever (20 pages = 1000 rows)
const MAX_PAGES = 20

// Loads every page of a list endpoint. Meant for small reference lists
// (venues, categories, teams) that the UI needs in full to look names up.
export async function fetchAllPages<T>(
  path: string,
  query: RequestOptions['query'] = {},
  signal?: AbortSignal,
): Promise<T[]> {
  const items: T[] = []
  for (let page = 1; page <= MAX_PAGES; page += 1) {
    const data = await apiFetch<Page<T>>(path, {
      query: { ...query, page },
      auth: false,
      signal,
    })
    items.push(...data.results)
    if (!data.next) break
  }
  return items
}
