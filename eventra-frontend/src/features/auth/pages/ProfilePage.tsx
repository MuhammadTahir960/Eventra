import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { PageHeader } from '@/components/PageHeader'
import { UserAvatar } from '@/components/UserAvatar'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { apiFetch, errorMessage, firstFieldErrors } from '@/lib/api-client'
import {
  PAYOUT_METHOD_LABEL,
  PROVIDER_LABEL,
  authStore,
  useAuth,
  type SessionUser,
} from '../auth-store'
import { DeleteAccountSection } from '../components/DeleteAccountSection'
import { usePageTitle } from '@/lib/use-page-title'

type Editable = Pick<SessionUser, 'first_name' | 'last_name' | 'gender'> & {
  provider: string
  holder_name: string
}

const ROLE_LABEL: Record<SessionUser['role'], string> = {
  attendee: 'Attendee',
  organizer: 'Organizer',
  admin: 'Admin',
}

export function ProfilePage() {
  usePageTitle('Profile')
  const { user } = useAuth()
  // RequireRole guarantees a signed-in user on this route
  const current = user as SessionUser
  const account = current.payout_account ?? null
  const [values, setValues] = useState<Editable>({
    first_name: current.first_name,
    last_name: current.last_name,
    gender: current.gender,
    provider: account?.provider ?? '',
    holder_name: account?.holder_name ?? '',
  })
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [status, setStatus] = useState<{
    tone: 'success' | 'error'
    text: string
  } | null>(null)
  const [pending, setPending] = useState(false)

  const payoutChanged =
    account !== null &&
    (values.provider !== account.provider ||
      values.holder_name !== account.holder_name)
  const changed =
    values.first_name !== current.first_name ||
    values.last_name !== current.last_name ||
    values.gender !== current.gender ||
    payoutChanged

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    const clientErrors: Record<string, string> = {}
    if (!values.first_name.trim())
      clientErrors.first_name = 'Enter your first name.'
    if (!values.last_name.trim())
      clientErrors.last_name = 'Enter your last name.'
    if (account && !values.provider.trim())
      clientErrors['payout_account.provider'] = 'Enter the bank or wallet.'
    if (account && !values.holder_name.trim())
      clientErrors['payout_account.holder_name'] =
        'Enter the account holder’s name.'
    setErrors(clientErrors)
    setStatus(null)
    if (Object.keys(clientErrors).length > 0) return

    setPending(true)
    try {
      const updated = await apiFetch<SessionUser>('/auth/me/', {
        method: 'PATCH',
        body: {
          first_name: values.first_name.trim(),
          last_name: values.last_name.trim(),
          gender: values.gender,
          ...(payoutChanged
            ? {
                payout_account: {
                  provider: values.provider.trim(),
                  holder_name: values.holder_name.trim(),
                },
              }
            : {}),
        },
      })
      authStore.setUser(updated)
      setStatus({ tone: 'success', text: 'Profile saved.' })
    } catch (caught) {
      const fields = firstFieldErrors(caught)
      setErrors(fields)
      if (Object.keys(fields).length === 0)
        setStatus({
          tone: 'error',
          text: errorMessage(
            caught,
            'Your profile could not be saved. Please try again.',
          ),
        })
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="gutter mx-auto flex max-w-[560px] flex-col gap-8 pt-10 sm:pt-14">
      <PageHeader title="Profile" />

      <div className="flex items-center gap-4">
        <UserAvatar
          user={{ ...current, ...values, avatar: current.avatar }}
          size={64}
        />
        <div>
          <p className="font-medium">{current.email}</p>
          <p className="text-sm text-muted-foreground">
            {ROLE_LABEL[current.role]} account
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
        {status && <Notice tone={status.tone}>{status.text}</Notice>}
        <div className="grid gap-5 sm:grid-cols-2">
          <FormField
            id="profile-first-name"
            label="First name"
            error={errors.first_name}
          >
            {(control) => (
              <Input
                {...control}
                value={values.first_name}
                maxLength={50}
                autoComplete="given-name"
                onChange={(event) =>
                  setValues({ ...values, first_name: event.target.value })
                }
              />
            )}
          </FormField>
          <FormField
            id="profile-last-name"
            label="Last name"
            error={errors.last_name}
          >
            {(control) => (
              <Input
                {...control}
                value={values.last_name}
                maxLength={50}
                autoComplete="family-name"
                onChange={(event) =>
                  setValues({ ...values, last_name: event.target.value })
                }
              />
            )}
          </FormField>
        </div>
        <FormField
          id="profile-gender"
          label="Gender"
          hint="Sets your avatar."
          error={errors.gender}
        >
          {(control) => (
            <NativeSelect
              {...control}
              value={values.gender}
              onChange={(event) =>
                setValues({
                  ...values,
                  gender: event.target.value as Editable['gender'],
                })
              }
            >
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </NativeSelect>
          )}
        </FormField>
        {account && (
          <section
            aria-labelledby="profile-payout-heading"
            className="flex flex-col gap-5 border-t border-border pt-6"
          >
            <div>
              <h2 id="profile-payout-heading" className="font-medium">
                Payout details
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {PAYOUT_METHOD_LABEL[account.method]} · {account.account_number}
                . The method and number can’t be changed.
              </p>
            </div>
            <div className="grid gap-5 sm:grid-cols-2">
              <FormField
                id="profile-payout-provider"
                label={PROVIDER_LABEL[account.method]}
                error={errors['payout_account.provider']}
              >
                {(control) => (
                  <Input
                    {...control}
                    value={values.provider}
                    maxLength={100}
                    onChange={(event) =>
                      setValues({ ...values, provider: event.target.value })
                    }
                  />
                )}
              </FormField>
              <FormField
                id="profile-payout-holder"
                label="Account holder"
                error={errors['payout_account.holder_name']}
              >
                {(control) => (
                  <Input
                    {...control}
                    value={values.holder_name}
                    maxLength={200}
                    onChange={(event) =>
                      setValues({ ...values, holder_name: event.target.value })
                    }
                  />
                )}
              </FormField>
            </div>
          </section>
        )}
        <Button
          type="submit"
          variant="ink"
          size="lg"
          className="w-fit"
          disabled={!changed || pending}
        >
          {pending ? 'Saving…' : 'Save changes'}
        </Button>
      </form>

      <section className="border-t border-border pt-6">
        <h2 className="font-medium">Password</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          To change your password, we email you a reset link.{' '}
          <Link
            to="/forgot-password"
            className="font-medium text-ember-deep underline-offset-4 hover:underline"
          >
            Send a reset link
          </Link>
        </p>
      </section>

      <DeleteAccountSection />
    </div>
  )
}
