import type { SessionUser } from '@/features/auth/auth-store'
import { initial } from '@/lib/initial'

// The backend sends a static asset key ("avatar-male" etc.) derived from
// gender, or null. Only known keys map to a file; anything else gets initials.
const AVATAR_FILES: Record<string, string> = {
  'avatar-male': '/avatars/avatar-male.svg',
  'avatar-female': '/avatars/avatar-female.svg',
  'avatar-other': '/avatars/avatar-other.svg',
}

export function UserAvatar({
  user,
  size = 32,
}: {
  user: Pick<SessionUser, 'first_name' | 'last_name' | 'avatar'>
  size?: number
}) {
  const src = user.avatar ? AVATAR_FILES[user.avatar] : undefined
  if (src) {
    return (
      <img
        src={src}
        alt=""
        width={size}
        height={size}
        className="shrink-0 rounded-full"
      />
    )
  }
  const initials = `${initial(user.first_name, '')}${initial(user.last_name, '')}`
  return (
    <span
      aria-hidden
      className="grid shrink-0 place-items-center rounded-full bg-muted font-medium text-foreground"
      style={{ width: size, height: size, fontSize: size * 0.38 }}
    >
      {initials || '?'}
    </span>
  )
}
