import { useState } from 'react'
import { FormField } from '@/components/FormField'
import { Input } from '@/components/ui/input'

interface PasswordFieldProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  autoComplete: 'current-password' | 'new-password'
  hint?: string
  error?: string
}

export function PasswordField({
  id,
  label,
  value,
  onChange,
  autoComplete,
  hint,
  error,
}: PasswordFieldProps) {
  const [visible, setVisible] = useState(false)

  return (
    <FormField id={id} label={label} hint={hint} error={error}>
      {(control) => (
        <div className="relative">
          <Input
            {...control}
            type={visible ? 'text' : 'password'}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            autoComplete={autoComplete}
            // Matches the backend's 128 character limit
            maxLength={128}
            className="pr-16"
          />
          <button
            type="button"
            onClick={() => setVisible((current) => !current)}
            aria-pressed={visible}
            aria-controls={id}
            className="absolute inset-y-0 right-0 rounded-md px-3 text-xs font-medium text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none"
          >
            {visible ? 'Hide' : 'Show'}
          </button>
        </div>
      )}
    </FormField>
  )
}
