import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useEffect, type ReactNode } from 'react'
import { Toaster } from 'sonner'
import { restoreSession } from '@/features/auth/session'
import { clearCacheOnUserChange } from './clear-cache-on-user-change'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Short freshness window avoids refetch storms on tab focus
      staleTime: 30_000,
      // One retry for network blips; 4xx errors are real answers, not flukes
      retry: 1,
    },
  },
})
clearCacheOnUserChange(queryClient)

export function AppProviders({ children }: { children: ReactNode }) {
  // After a reload, re-validate the saved refresh token and load the profile
  useEffect(() => {
    void restoreSession()
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      {/* Short confirmations only ("Event cancelled"); form errors stay inline */}
      <Toaster
        position="bottom-center"
        offset={{ bottom: 'max(16px, env(safe-area-inset-bottom))' }}
        mobileOffset={{ bottom: 'calc(88px + env(safe-area-inset-bottom))' }}
        toastOptions={{
          // Sonner's default description grey is unreadable on ink
          classNames: { description: '!text-[#c9c7c0]' },
          style: {
            background: 'var(--ink)',
            color: 'var(--paper)',
            border: '1px solid var(--ink)',
            borderRadius: '10px',
            fontFamily: 'var(--font-sans)',
            fontSize: '14px',
          },
        }}
      />
    </QueryClientProvider>
  )
}
