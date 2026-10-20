import { Outlet, ScrollRestoration, useNavigation } from 'react-router-dom'

// Wraps both shells: new pages open at the top, Back restores where you were,
// and a thin bar shows while a lazy page chunk loads.
export function RootLayout() {
  const loading = useNavigation().state === 'loading'
  return (
    <>
      {loading && (
        <div
          aria-hidden
          className="nav-progress fixed inset-x-0 top-0 z-[60] h-0.5 origin-left bg-ember"
        />
      )}
      <ScrollRestoration />
      <Outlet />
    </>
  )
}
