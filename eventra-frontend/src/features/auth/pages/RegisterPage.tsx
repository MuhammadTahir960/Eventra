import { useEffect, useState, type FormEvent } from 'react'
import { Link, Navigate, useSearchParams } from 'react-router-dom'
import { ErrorSummary, type ErrorItem } from '@/components/ErrorSummary'
import { FormField } from '@/components/FormField'
import { Notice } from '@/components/Notice'
import { Button } from '@/components/ui/button'
import { ButtonLink } from '@/components/ui/button-link'
import { Input } from '@/components/ui/input'
import { NativeSelect } from '@/components/ui/native-select'
import { ApiError, errorMessage, firstFieldErrors } from '@/lib/api-client'
import { authApi, type IssuedAccountNumber, type RegisterPayload } from '../api'
import {
  PAYOUT_METHOD_LABEL,
  PROVIDER_LABEL,
  type PayoutMethod,
} from '../auth-store'
import { AuthLayout } from '../components/AuthLayout'
import { PasswordField } from '../components/PasswordField'
import { Turnstile } from '../components/Turnstile'
import { useAuth } from '../auth-store'
import { ROLE_HOME } from '../role-routes'
import { usePageTitle } from '@/lib/use-page-title'

type FieldName =
  | 'first_name'
  | 'last_name'
  | 'email'
  | 'password'
  | 'gender'
  | 'role'
  | 'method'
  | 'provider'
  | 'holder_name'
  | 'account_number'

interface PayoutDraft {
  method: PayoutMethod | ''
  provider: string
  holder_name: string
}

type Errors = Partial<Record<FieldName, string>>

// DOM ids, so the error summary can focus the right control
const FIELD_ID: Record<FieldName, string> = {
  first_name: 'reg-first-name',
  last_name: 'reg-last-name',
  email: 'reg-email',
  password: 'reg-password',
  gender: 'reg-gender',
  role: 'reg-role-attendee',
  method: 'reg-payout-method',
  provider: 'reg-payout-provider',
  holder_name: 'reg-payout-holder',
  account_number: 'reg-payout-number',
}

// The server's nested keys, mapped onto this form's fields
const PAYOUT_FIELD: Record<string, FieldName> = {
  'payout_account.method': 'method',
  'payout_account.provider': 'provider',
  'payout_account.holder_name': 'holder_name',
  'payout_account.number_token': 'account_number',
}

// Quick checks to save a round trip. The server validates everything again
// (password strength, duplicate email) and its answer is the one that counts.
function validate(
  values: Partial<RegisterPayload>,
  payout: PayoutDraft,
  issued: IssuedAccountNumber | null,
): Errors {
  const errors: Errors = {}
  if (!values.first_name?.trim()) errors.first_name = 'Enter your first name.'
  if (!values.last_name?.trim()) errors.last_name = 'Enter your last name.'
  if (!values.email?.includes('@'))
    errors.email = 'Enter a valid email address.'
  if (!values.password || values.password.length < 8) {
    errors.password = 'Use at least 8 characters.'
  }
  if (!values.gender) errors.gender = 'Choose an option.'
  if (!values.role) errors.role = 'Choose how you will use Eventra.'
  if (values.role === 'organizer') {
    if (!payout.method) errors.method = 'Choose how you want to be paid.'
    if (!payout.provider.trim()) errors.provider = 'Enter the bank or wallet.'
    if (!payout.holder_name.trim())
      errors.holder_name = 'Enter the account holder’s name.'
    if (!issued) errors.account_number = 'Wait for your account number.'
  }
  return errors
}

const ROLE_OPTIONS = [
  {
    value: 'attendee',
    label: 'Attendee',
    description: 'Browse events and buy tickets.',
  },
  {
    value: 'organizer',
    label: 'Organizer',
    description:
      'Create events. An admin approves each one before it goes live.',
  },
] as const

export function RegisterPage() {
  usePageTitle('Create account')
  const { user } = useAuth()
  // "Become an organizer" links preselect the organizer role
  const [params] = useSearchParams()
  const [values, setValues] = useState<Partial<RegisterPayload>>(() =>
    params.get('role') === 'organizer' ? { role: 'organizer' } : {},
  )
  const [errors, setErrors] = useState<Errors>({})
  const [formError, setFormError] = useState<string | null>(null)
  const [focusKey, setFocusKey] = useState(0)
  const [pending, setPending] = useState(false)
  const [registeredEmail, setRegisteredEmail] = useState<string | null>(null)
  const [captchaToken, setCaptchaToken] = useState<string | null>(null)
  const [captchaKey, setCaptchaKey] = useState(0)
  const [payout, setPayout] = useState<PayoutDraft>({
    method: '',
    provider: '',
    holder_name: '',
  })
  // Eventra assigns the number; the form only shows it, locked
  const [issued, setIssued] = useState<IssuedAccountNumber | null>(null)
  const isOrganizer = values.role === 'organizer'
  // Kept across role switches; cleared (and so re-fetched) only when the server refuses it
  useEffect(() => {
    if (!isOrganizer || issued) return
    let cancelled = false
    authApi
      .issueAccountNumber()
      .then((number) => !cancelled && setIssued(number))
      .catch(
        (caught) =>
          !cancelled &&
          setErrors((current) => ({
            ...current,
            account_number: errorMessage(
              caught,
              'We couldn’t get your account number. Reload the page.',
            ),
          })),
      )
    return () => {
      cancelled = true
    }
  }, [isOrganizer, issued])

  if (user) return <Navigate to={ROLE_HOME[user.role]} replace />

  // Check-your-email screen: the account stays inactive until verified
  if (registeredEmail) {
    return (
      <AuthLayout title="Check your email">
        <Notice tone="success">
          We sent an email to{' '}
          <strong className="break-all">{registeredEmail}</strong>. Follow it to
          finish signing up, then sign in. If you already have an account, the
          email says how to get back in.
        </Notice>
        <ButtonLink variant="ink" size="lg" className="w-full" to="/login">
          Go to sign in
        </ButtonLink>
      </AuthLayout>
    )
  }

  function setField<K extends keyof RegisterPayload>(
    name: K,
    value: RegisterPayload[K] | '',
  ) {
    setValues((current) => ({ ...current, [name]: value }))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setFormError(null)

    const clientErrors = validate(values, payout, issued)
    if (Object.keys(clientErrors).length > 0) {
      setErrors(clientErrors)
      setFocusKey((key) => key + 1)
      return
    }
    setErrors({})
    if (!captchaToken) {
      setFormError("Please confirm you're human first.")
      return
    }

    setPending(true)
    try {
      const created = await authApi.register({
        ...(values as RegisterPayload),
        captcha_token: captchaToken,
        ...(isOrganizer && issued
          ? {
              payout_account: {
                method: payout.method as PayoutMethod,
                provider: payout.provider.trim(),
                holder_name: payout.holder_name.trim(),
                number_token: issued.token,
              },
            }
          : {}),
      })
      setRegisteredEmail(created.email)
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        (caught.status === 400 || caught.status === 409)
      ) {
        // Map the backend's per-field messages onto our form
        const server = firstFieldErrors(caught)
        const serverErrors: Errors = {}
        for (const name of Object.keys(FIELD_ID) as FieldName[]) {
          if (server[name]) serverErrors[name] = server[name]
        }
        for (const [key, name] of Object.entries(PAYOUT_FIELD)) {
          if (server[key]) serverErrors[name] = server[key]
        }
        if (server.payout_account) setFormError(server.payout_account)
        // An expired or already-used number: show a fresh one
        if (serverErrors.account_number) {
          setIssued(null)
          serverErrors.account_number = `${serverErrors.account_number} We’ve given you a new one.`
        }
        // DRF's unique-field message is lower-case model wording
        if (serverErrors.email?.includes('already exists')) {
          serverErrors.email =
            'An account with this email already exists. Sign in instead, or reset your password.'
        }
        setErrors(serverErrors)
        if (Object.keys(serverErrors).length === 0) setFormError(caught.message)
        setFocusKey((key) => key + 1)
      } else {
        // 429 (5 sign-ups per hour) and server errors
        setFormError(
          errorMessage(caught, 'Something went wrong. Please try again.'),
        )
      }
    } finally {
      setPending(false)
      // Each check works once: get a fresh one for the next try
      setCaptchaKey((key) => key + 1)
    }
  }

  const summary: ErrorItem[] = (Object.keys(FIELD_ID) as FieldName[]).flatMap(
    (name) => {
      const message = errors[name]
      return message ? [{ fieldId: FIELD_ID[name], message }] : []
    },
  )

  return (
    <AuthLayout
      title="Create your account"
      footer={
        <>
          Already registered?{' '}
          <Link
            to="/login"
            className="font-medium text-ember-deep underline-offset-4 hover:underline"
          >
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-5" noValidate>
        <ErrorSummary errors={summary} focusKey={focusKey} />
        {formError && <Notice tone="error">{formError}</Notice>}

        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            id={FIELD_ID.first_name}
            label="First name"
            error={errors.first_name}
          >
            {(control) => (
              <Input
                {...control}
                value={values.first_name ?? ''}
                onChange={(event) => setField('first_name', event.target.value)}
                autoComplete="given-name"
                maxLength={50}
              />
            )}
          </FormField>
          <FormField
            id={FIELD_ID.last_name}
            label="Last name"
            error={errors.last_name}
          >
            {(control) => (
              <Input
                {...control}
                value={values.last_name ?? ''}
                onChange={(event) => setField('last_name', event.target.value)}
                autoComplete="family-name"
                maxLength={50}
              />
            )}
          </FormField>
        </div>

        <FormField id={FIELD_ID.email} label="Email" error={errors.email}>
          {(control) => (
            <Input
              {...control}
              type="email"
              spellCheck={false}
              value={values.email ?? ''}
              onChange={(event) => setField('email', event.target.value)}
              autoComplete="email"
            />
          )}
        </FormField>

        <PasswordField
          id={FIELD_ID.password}
          label="Password"
          value={values.password ?? ''}
          onChange={(value) => setField('password', value)}
          autoComplete="new-password"
          hint="At least 8 characters. Not too common, not all numbers."
          error={errors.password}
        />

        <FormField id={FIELD_ID.gender} label="Gender" error={errors.gender}>
          {(control) => (
            <NativeSelect
              {...control}
              value={values.gender ?? ''}
              onChange={(event) =>
                setField(
                  'gender',
                  event.target.value as RegisterPayload['gender'],
                )
              }
            >
              <option value="" disabled>
                Select…
              </option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </NativeSelect>
          )}
        </FormField>

        {/* Admin can never be chosen here; the backend rejects it too */}
        <fieldset aria-describedby={errors.role ? 'reg-role-error' : undefined}>
          <legend className="mb-1.5 text-sm font-medium">
            I want to use Eventra as
          </legend>
          <div className="grid gap-2">
            {ROLE_OPTIONS.map((option) => (
              <label
                key={option.value}
                htmlFor={`reg-role-${option.value}`}
                className="flex cursor-pointer items-start gap-3 rounded-md border p-3 border-hairline-strong bg-card has-[:checked]:border-ink has-[:checked]:ring-1 has-[:checked]:ring-ink has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring/40"
              >
                <input
                  type="radio"
                  id={`reg-role-${option.value}`}
                  name="role"
                  value={option.value}
                  checked={values.role === option.value}
                  onChange={() => setField('role', option.value)}
                  className="mt-1 accent-[var(--ink)]"
                />
                <span>
                  <span className="block text-sm font-medium">
                    {option.label}
                  </span>
                  <span className="block text-xs text-muted-foreground">
                    {option.description}
                  </span>
                </span>
              </label>
            ))}
          </div>
          {errors.role && (
            <p id="reg-role-error" className="mt-1.5 text-sm text-danger">
              {errors.role}
            </p>
          )}
        </fieldset>

        {isOrganizer && (
          <fieldset className="flex flex-col gap-4">
            <legend className="mb-1.5 text-sm font-medium">
              Payout details
            </legend>
            <p className="-mt-2 text-xs text-muted-foreground">
              Where Eventra sends your ticket money after each event.
            </p>
            <FormField
              id={FIELD_ID.method}
              label="Paid to"
              error={errors.method}
            >
              {(control) => (
                <NativeSelect
                  {...control}
                  value={payout.method}
                  onChange={(event) =>
                    setPayout({
                      ...payout,
                      method: event.target.value as PayoutMethod,
                    })
                  }
                >
                  <option value="" disabled>
                    Select…
                  </option>
                  {Object.entries(PAYOUT_METHOD_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </NativeSelect>
              )}
            </FormField>
            <div className="grid gap-4 sm:grid-cols-2">
              <FormField
                id={FIELD_ID.provider}
                label={PROVIDER_LABEL[payout.method || 'bank']}
                error={errors.provider}
              >
                {(control) => (
                  <Input
                    {...control}
                    value={payout.provider}
                    maxLength={100}
                    onChange={(event) =>
                      setPayout({ ...payout, provider: event.target.value })
                    }
                  />
                )}
              </FormField>
              <FormField
                id={FIELD_ID.holder_name}
                label="Account holder"
                error={errors.holder_name}
              >
                {(control) => (
                  <Input
                    {...control}
                    value={payout.holder_name}
                    maxLength={200}
                    autoComplete="name"
                    onChange={(event) =>
                      setPayout({ ...payout, holder_name: event.target.value })
                    }
                  />
                )}
              </FormField>
            </div>
            <FormField
              id={FIELD_ID.account_number}
              label="Account number"
              hint="Assigned by Eventra. It can’t be changed."
              error={errors.account_number}
            >
              {(control) => (
                <Input
                  {...control}
                  readOnly
                  value={
                    issued
                      ? issued.number.replace(/(\d{4})(?=\d)/g, '$1 ')
                      : 'Getting your number…'
                  }
                  className="bg-muted font-mono tabular-nums"
                />
              )}
            </FormField>
          </fieldset>
        )}

        <Turnstile onToken={setCaptchaToken} resetKey={captchaKey} />

        <Button
          type="submit"
          variant="ink"
          size="lg"
          className="w-full"
          disabled={pending}
        >
          {pending ? 'Creating account…' : 'Create account'}
        </Button>
      </form>
    </AuthLayout>
  )
}
