import { useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { ApiError } from '@/lib/api-client'
import { authApi } from '../api'
import { AuthLayout } from '../components/AuthLayout'
import { PasswordField } from '../components/PasswordField'
import { authStore } from '../auth-store'
import { usePageTitle } from '@/lib/use-page-title'

// Step 2 of a reset: the emailed link opens this page with ?token=...
export function ResetPasswordPage() {
  usePageTitle('Choose a new password')
  const [params] = useSearchParams()
  const token = params.get('token')

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [passwordError, setPasswordError] = useState<string | undefined>()
  const [confirmError, setConfirmError] = useState<string | undefined>()
  const [formError, setFormError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const [done, setDone] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)
    setPasswordError(undefined)
    setConfirmError(undefined)

    if (password.length < 8) {
      setPasswordError('Use at least 8 characters.')
      return
    }
    if (password !== confirm) {
      setConfirmError('The passwords do not match.')
      return
    }

    setPending(true)
    try {
      await authApi.confirmPasswordReset(token ?? '', password)
      // The backend signs the account out everywhere after a reset
      authStore.clear()
      setDone(true)
    } catch (caught) {
      if (caught instanceof ApiError && caught.fieldErrors.new_password) {
        // Strength rules (too common, all numeric, ...)
        setPasswordError(caught.fieldErrors.new_password[0])
      } else if (caught instanceof ApiError) {
        // Invalid or expired link, or rate limited
        setFormError(caught.message)
      } else {
        setFormError('Something went wrong. Please try again.')
      }
    } finally {
      setPending(false)
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Reset your password">
        <Notice tone="error">
          This link is missing its reset code. Request a new one.
        </Notice>
        <ButtonLink
          variant="ink"
          size="lg"
          className="w-full"
          to="/forgot-password"
        >
          Request a reset link
        </ButtonLink>
      </AuthLayout>
    )
  }

  if (done) {
    return (
      <AuthLayout title="Password updated">
        <Notice tone="success">
          Your password was changed. Sign in with the new one.
        </Notice>
        <ButtonLink variant="ink" size="lg" className="w-full" to="/login">
          Sign in
        </ButtonLink>
      </AuthLayout>
    )
  }

  return (
    <AuthLayout title="Choose a new password">
      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
        {formError && (
          <Notice tone="error">
            {formError}{' '}
            <Link to="/forgot-password" className="underline">
              Request a new link
            </Link>
          </Notice>
        )}
        <PasswordField
          id="reset-password"
          label="New password"
          value={password}
          onChange={setPassword}
          autoComplete="new-password"
          hint="At least 8 characters. Not too common, not all numbers."
          error={passwordError}
        />
        <PasswordField
          id="reset-confirm"
          label="Confirm new password"
          value={confirm}
          onChange={setConfirm}
          autoComplete="new-password"
          error={confirmError}
        />
        <Button
          type="submit"
          variant="ink"
          size="lg"
          className="w-full"
          disabled={pending}
        >
          {pending ? 'Saving…' : 'Save new password'}
        </Button>
      </form>
    </AuthLayout>
  )
}
