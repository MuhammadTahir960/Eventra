import { useSearchParams } from 'react-router-dom'
import { EmptyState } from '@/components/EmptyState'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { Pagination } from '@/components/Pagination'
import { StatusBadge } from '@/components/StatusBadge'
import { UserAvatar } from '@/components/UserAvatar'
import { NativeSelect } from '@/components/ui/native-select'
import { pageParam } from '@/lib/ids'
import { useAdminUsers, type AdminUserFilters } from '../api'
import { usePageTitle } from '@/lib/use-page-title'
import { LoadingBlock } from '@/components/LoadingBlock'
import { SearchForm } from '@/components/SearchForm'
import { TableFrame } from '@/components/TableFrame'
import { formatDateTime } from '@/lib/format'

const ROLE_LABEL = {
  attendee: 'Attendee',
  organizer: 'Organizer',
  admin: 'Admin',
} as const

export function UsersPage() {
  usePageTitle('Users')
  // Filters live in the URL (see AdminEventsPage), checked against an allow-list
  const [params, setParams] = useSearchParams()
  const role = params.get('role') ?? ''
  const filters: AdminUserFilters = {
    search: (params.get('q') ?? '').slice(0, 100),
    role: Object.hasOwn(ROLE_LABEL, role)
      ? (role as AdminUserFilters['role'])
      : '',
    page: pageParam(params.get('page')),
  }
  function setFilters(next: AdminUserFilters) {
    const query: Record<string, string> = {}
    if (next.search) query.q = next.search
    if (next.role) query.role = next.role
    if (next.page > 1) query.page = String(next.page)
    setParams(query)
  }
  const users = useAdminUsers(filters)
  const list = users.data?.results ?? []

  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        size="md"
        title="Users"
        description="Everyone with an account. Roles can only be changed in Django admin."
      />

      <div className="flex flex-col gap-3 sm:flex-row">
        <SearchForm
          id="user-search"
          label="Search by email"
          placeholder="Search by email…"
          value={filters.search}
          onSearch={(search) => setFilters({ ...filters, search, page: 1 })}
        />
        <label htmlFor="user-role" className="sr-only">
          Role
        </label>
        <NativeSelect
          id="user-role"
          className="sm:w-44"
          value={filters.role}
          onChange={(e) =>
            setFilters({
              ...filters,
              role: e.target.value as AdminUserFilters['role'],
              page: 1,
            })
          }
        >
          <option value="">All roles</option>
          <option value="attendee">Attendees</option>
          <option value="organizer">Organizers</option>
          <option value="admin">Admins</option>
        </NativeSelect>
      </div>

      {users.isError ? (
        <Notice tone="error">{users.error.message}</Notice>
      ) : users.isPending ? (
        <LoadingBlock label="Loading users" className="h-64" />
      ) : list.length === 0 ? (
        <EmptyState title="No users match" body="Try another email or role." />
      ) : (
        <>
          <TableFrame dimmed={users.isPlaceholderData}>
            <thead>
              <tr>
                <th scope="col">User</th>
                <th scope="col">Role</th>
                <th scope="col">Account</th>
                <th scope="col">Joined</th>
              </tr>
            </thead>
            <tbody>
              {list.map((user) => (
                <tr key={user.id}>
                  <td className="min-w-64">
                    <span className="flex items-center gap-3">
                      <UserAvatar user={user} size={32} />
                      <span className="min-w-0">
                        <span className="block font-medium">
                          {user.first_name} {user.last_name}
                        </span>
                        <span className="block truncate text-[13px] text-muted-foreground">
                          {user.email}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td>{ROLE_LABEL[user.role]}</td>
                  <td>
                    <StatusBadge tone={user.is_active ? 'success' : 'neutral'}>
                      {user.is_active ? 'Active' : 'Inactive'}
                    </StatusBadge>
                  </td>
                  <td className="tabular text-muted-foreground">
                    {formatDateTime(user.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </TableFrame>
          <Pagination
            page={filters.page}
            count={users.data.count}
            hasPrevious={Boolean(users.data.previous)}
            hasNext={Boolean(users.data.next)}
            onPage={(page) => setFilters({ ...filters, page })}
          />
        </>
      )}
    </div>
  )
}
