import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import { FormField } from '@/components/FormField'
import { HoldToConfirmButton } from '@/components/HoldToConfirmButton'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  ApiError,
  apiFetch,
  errorMessage,
  firstFieldErrors,
} from '@/lib/api-client'
import { authStore } from '../auth-store'

// Wipes the user's personal details; payment records stay. The server refuses
// (409, with reasons) while tickets, events or money are still in flight.
export function DeleteAccountSection() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [password, setPassword] = useState('')
  const [pending, setPending] = useState(false)
  const [passwordError, setPasswordError] = useState<string>()
  const [blocked, setBlocked] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  // Bumped after a failure so the hold button re-arms
  const [attempt, setAttempt] = useState(0)

  function clearMessages() {
    setPasswordError(undefined)
    setBlocked([])
    setError(null)
  }

  async function confirm() {
    clearMessages()
    if (!password) {
      setPasswordError('Enter your password.')
      setAttempt((n) => n + 1)
      return
    }
    setPending(true)
    try {
      await apiFetch('/auth/me/deletion/', {
        method: 'POST',
        body: { password },
      })
      // The server has already signed this account out everywhere
      authStore.clear()
      toast.success('Your account has been deleted')
      // Signing out makes this page's guard head for /login; going home on the
      // next tick overrides it (navigating first loses the race to the guard)
      setTimeout(() => void navigate('/', { replace: true }), 0)
    } catch (caught) {
      const fromServer = firstFieldErrors(caught).password
      if (caught instanceof ApiError && caught.status === 409)
        setBlocked(caught.fieldErrors.reasons ?? [caught.message])
      else if (fromServer) setPasswordError(fromServer)
      else setError(errorMessage(caught, 'Your account could not be deleted.'))
      setAttempt((n) => n + 1)
    } finally {
      setPending(false)
    }
  }

  return (
    <section className="border-t border-border pt-6">
      <h2 className="font-medium">Delete account</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Removes your name and email from Eventra and signs you out everywhere.
        Records of past payments are kept.
      </p>
      <ConfirmDialog
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (!next) {
            setPassword('')
            clearMessages()
          }
        }}
        trigger={
          <Button variant="destructive" className="mt-4">
            Delete account
          </Button>
        }
        title="Delete your account?"
        description="Your name and email are removed and you're signed out on every device. This can't be undone."
        confirmLabel="Delete account"
        destructive
        pending={pending}
        onConfirm={confirm}
        confirmControl={
          <HoldToConfirmButton
            key={attempt}
            label="Hold to delete account"
            confirmedLabel="Deleting…"
            hintId="delete-account-hint"
            disabled={pending}
            onConfirm={() => void confirm()}
          />
        }
      >
        <FormField
          id="delete-account-password"
          label="Your password"
          error={passwordError}
        >
          {(control) => (
            <Input
              {...control}
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value)
                setPasswordError(undefined)
              }}
            />
          )}
        </FormField>
        <p
          id="delete-account-hint"
          className="mt-3 text-[13px] text-muted-foreground"
        >
          Press and hold the button until it fills to confirm.
        </p>
        {blocked.length > 0 && (
          <Notice tone="error" className="mt-3">
            <p>Your account can't be deleted yet:</p>
            <ul className="mt-1 list-disc pl-5">
              {blocked.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          </Notice>
        )}
        {error && (
          <Notice tone="error" className="mt-3">
            {error}
          </Notice>
        )}
      </ConfirmDialog>
    </section>
  )
}
