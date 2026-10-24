import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { keepPreviousData } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { Page } from '@/lib/pagination'
import type { SessionUser } from '@/features/auth/auth-store'
import type { EventItem, EventStatus } from '@/features/events/types'

// ---------- moderation ----------

export function usePendingEvents() {
  return useQuery({
    queryKey: ['admin', 'pending'],
    queryFn: ({ signal }) =>
      apiFetch<Page<EventItem>>('/admin/events/pending/', { signal }),
  })
}

function useAdminEventAction<TVars>(
  request: (vars: TVars) => Promise<unknown>,
) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: request,
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['admin'] })
      void client.invalidateQueries({ queryKey: ['events'] })
    },
  })
}

export const useApproveEvent = () =>
  useAdminEventAction((id: string) =>
    apiFetch<EventItem>(`/admin/events/${id}/approve/`, { method: 'POST' }),
  )

export const useRejectEvent = () =>
  useAdminEventAction(({ id, reason }: { id: string; reason: string }) =>
    apiFetch<EventItem>(`/admin/events/${id}/reject/`, {
      method: 'POST',
      body: { reason },
    }),
  )

// Re-queues refunds that failed after a cancellation (202, runs in Celery)
export const useRetryRefunds = () =>
  useAdminEventAction((id: string) =>
    apiFetch<void>(`/admin/events/${id}/retry-refunds/`, { method: 'POST' }),
  )

// ---------- all events ----------

export interface AdminEventFilters {
  status: EventStatus | ''
  search: string
  page: number
}

export function useAdminEvents(filters: AdminEventFilters) {
  return useQuery({
    queryKey: ['admin', 'events', filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<EventItem>>('/events/', {
        // Admins also see soft-deleted events with this flag
        query: {
          include_inactive: true,
          status: filters.status,
          search: filters.search.trim(),
          page: filters.page,
        },
        signal,
      }),
    placeholderData: keepPreviousData,
  })
}

// ---------- users ----------

export interface AdminUserFilters {
  search: string
  role: SessionUser['role'] | ''
  page: number
}

export type AdminUser = SessionUser & { is_active: boolean; created_at: string }

export function useAdminUsers(filters: AdminUserFilters) {
  return useQuery({
    queryKey: ['admin', 'users', filters],
    queryFn: ({ signal }) =>
      apiFetch<Page<AdminUser>>('/admin/users/', {
        query: {
          search: filters.search.trim(),
          role: filters.role,
          page: filters.page,
        },
        signal,
      }),
    placeholderData: keepPreviousData,
  })
}
