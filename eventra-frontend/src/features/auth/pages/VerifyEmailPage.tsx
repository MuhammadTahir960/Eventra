import { useQuery } from '@tanstack/react-query'
import { useSearchParams } from 'react-router-dom'
import { Notice } from '@/components/Notice'
import { ButtonLink } from '@/components/ui/button-link'
import { ApiError } from '@/lib/api-client'
import { authApi } from '../api'
import { AuthLayout } from '../components/AuthLayout'
import { usePageTitle } from '@/lib/use-page-title'

export function VerifyEmailPage() {
  usePageTitle('Verify your email')
  const [params] = useSearchParams()
  const token = params.get('token')

  const result = useQuery({
    queryKey: ['verify-email', token],
    queryFn: () => authApi.verifyEmail(token ?? ''),
    enabled: Boolean(token),
    retry: false,
    staleTime: Infinity,
  })

  return (
    <AuthLayout title="Email verification">
      {!token && (
        <Notice tone="error">
          This link is missing its verification code. Open the link from your
          email again.
        </Notice>
      )}
      {token && result.isPending && <Notice>Verifying your email…</Notice>}
      {result.isError && (
        <Notice tone="error">
          {result.error instanceof ApiError
            ? result.error.message
            : 'We could not verify your email. Please try again.'}
        </Notice>
      )}
      {result.isSuccess && (
        <>
          <Notice tone="success">{result.data.detail}</Notice>
          <ButtonLink variant="ink" size="lg" className="w-full" to="/login">
            Sign in
          </ButtonLink>
        </>
      )}
    </AuthLayout>
  )
}
