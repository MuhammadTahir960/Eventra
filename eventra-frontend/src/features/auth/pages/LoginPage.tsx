import { useState, type FormEvent } from 'react'
import { Link, Navigate, useLocation } from 'react-router-dom'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ApiError } from '@/lib/api-client'
import { AuthLayout } from '../components/AuthLayout'
import { PasswordField } from '../components/PasswordField'
import { useAuth } from '../auth-store'
import { safeRedirect } from '../redirect'
import { ROLE_HOME } from '../role-routes'
import { signIn } from '../session'
import { usePageTitle } from '@/lib/use-page-title'

export function LoginPage() {
  usePageTitle('Sign in')
  const { user } = useAuth()
  const location = useLocation()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  // Already signed in (or just signed in): go to the page they wanted,
  // or the home screen for their role
  if (user) {
    const from = safeRedirect(
      (location.state as { from?: unknown } | null)?.from,
    )
    return <Navigate to={from ?? ROLE_HOME[user.role]} replace />
  }

  async function attempt(loginEmail: string, loginPassword: string) {
    setError(null)
    setPending(true)
    try {
      // On success the store updates and the redirect above takes over
      await signIn(loginEmail, loginPassword)
    } catch (caught) {
      setError(
        // 401 covers a wrong password and an account not yet verified; the
        // library's wording ("No active account found...") explains neither
        caught instanceof ApiError && caught.status === 401
          ? "That email and password don't match an active account. If you just signed up, open the verification link we emailed you first."
          : caught instanceof ApiError
            ? caught.message
            : 'Something went wrong. Please try again.',
      )
      setPending(false)
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!email.trim() || !password) {
      setError('Enter your email and password.')
      return
    }
    void attempt(email.trim(), password)
  }

  return (
    <AuthLayout
      title="Sign in"
      description="Welcome back. Use the email you registered with."
      footer={
        <>
          New to Eventra?{' '}
          <Link
            to="/register"
            className="font-medium text-ember-deep underline-offset-4 hover:underline"
          >
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
        {error && <Notice tone="error">{error}</Notice>}

        <FormField id="login-email" label="Email">
          {(control) => (
            <Input
              {...control}
              type="email"
              spellCheck={false}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="email"
              required
            />
          )}
        </FormField>

        <PasswordField
          id="login-password"
          label="Password"
          value={password}
          onChange={setPassword}
          autoComplete="current-password"
        />

        <div className="text-right text-sm">
          <Link
            to="/forgot-password"
            className="font-medium text-ember-deep underline-offset-4 hover:underline"
          >
            Forgot your password?
          </Link>
        </div>

        <Button
          type="submit"
          variant="ink"
          size="lg"
          className="w-full"
          disabled={pending}
        >
          {pending ? 'Signing in…' : 'Sign in'}
        </Button>
      </form>
    </AuthLayout>
  )
}
