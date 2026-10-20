import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { ApiError } from '@/lib/api-client'
import { authApi } from '../api'
import { AuthLayout } from '../components/AuthLayout'
import { usePageTitle } from '@/lib/use-page-title'

// Step 1 of a reset. The backend always answers the same way, whether or not
// the email has an account, so this screen never reveals which emails exist.
export function ForgotPasswordPage() {
  usePageTitle('Reset your password')
  const [email, setEmail] = useState('')
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setPending(true)
    try {
      await authApi.requestPasswordReset(email.trim())
      setSent(true)
    } catch (caught) {
      // Mostly the 5-per-hour limit
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Something went wrong. Please try again.',
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <AuthLayout
      title="Reset your password"
      description="Enter your email and we'll send you a reset link."
      footer={
        <Link
          to="/login"
          className="font-medium text-ember-deep underline-offset-4 hover:underline"
        >
          Back to sign in
        </Link>
      }
    >
      {sent ? (
        <Notice tone="success">
          If an account exists for that email, a reset link is on its way. It
          expires in 1 hour.
        </Notice>
      ) : (
        <form
          onSubmit={handleSubmit}
          className="flex flex-col gap-5"
          noValidate
        >
          {error && <Notice tone="error">{error}</Notice>}
          <FormField id="forgot-email" label="Email">
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
          <Button
            type="submit"
            variant="ink"
            size="lg"
            className="w-full"
            disabled={pending || !email}
          >
            {pending ? 'Sending…' : 'Send reset link'}
          </Button>
        </form>
      )}
    </AuthLayout>
  )
}
