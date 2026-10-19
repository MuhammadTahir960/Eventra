import { Menu } from '@base-ui/react/menu'
import { HugeiconsIcon } from '@hugeicons/react'
import { ArrowDown01Icon } from '@hugeicons/core-free-icons'
import { Link, useNavigate } from 'react-router-dom'
import type { SessionUser } from '@/features/auth/auth-store'
import { ROLE_HOME, WORKSPACE_LABEL } from '@/features/auth/role-routes'
import { signOut } from '@/features/auth/session'
import { UserAvatar } from './UserAvatar'

const itemClass =
  'flex h-9 cursor-default items-center rounded-md px-2.5 text-sm text-foreground outline-none select-none data-highlighted:bg-muted'

export function AccountMenu({ user }: { user: SessionUser }) {
  const navigate = useNavigate()
  const workspace = user.role === 'attendee' ? null : user.role

  return (
    <Menu.Root>
      <Menu.Trigger
        className="flex h-10 items-center gap-2 rounded-full py-1 pr-2 pl-1 text-sm font-medium hover:bg-muted aria-expanded:bg-muted"
        aria-label="Account menu"
      >
        <UserAvatar user={user} size={32} />
        <span className="hidden max-w-32 truncate sm:inline">
          {user.first_name}
        </span>
        <HugeiconsIcon icon={ArrowDown01Icon} size={16} aria-hidden />
      </Menu.Trigger>
      <Menu.Portal>
        <Menu.Positioner sideOffset={6} align="end" className="z-50">
          <Menu.Popup className="w-60 origin-(--transform-origin) rounded-lg border border-border bg-popover p-1.5 shadow-overlay transition-[opacity,scale] duration-200 ease-out data-ending-style:scale-95 motion-reduce:data-starting-style:scale-100 motion-reduce:data-ending-style:scale-100 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0">
            <div className="px-2.5 pt-1.5 pb-2">
              <p className="truncate text-sm font-medium">
                {user.first_name} {user.last_name}
              </p>
              <p className="truncate text-[13px] text-muted-foreground">
                {user.email}
              </p>
            </div>
            <Menu.Separator className="mx-1 my-1 h-px bg-border" />
            <Menu.LinkItem
              render={<Link to="/bookings" />}
              className={itemClass}
            >
              My tickets
            </Menu.LinkItem>
            <Menu.LinkItem
              render={<Link to="/profile" />}
              className={itemClass}
            >
              Profile
            </Menu.LinkItem>
            {workspace && (
              <Menu.LinkItem
                render={<Link to={ROLE_HOME[workspace]} />}
                className={itemClass}
              >
                {WORKSPACE_LABEL[workspace]}
              </Menu.LinkItem>
            )}
            <Menu.Separator className="mx-1 my-1 h-px bg-border" />
            <Menu.Item
              className={itemClass}
              onClick={() => {
                void signOut().then(() => navigate('/'))
              }}
            >
              Sign out
            </Menu.Item>
          </Menu.Popup>
        </Menu.Positioner>
      </Menu.Portal>
    </Menu.Root>
  )
}
