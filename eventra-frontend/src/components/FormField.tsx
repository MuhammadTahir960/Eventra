import type { ReactNode } from 'react'

// Props the wrapped control needs to be announced correctly by screen readers
export interface FieldControlProps {
  id: string
  'aria-describedby': string | undefined
  'aria-invalid': true | undefined
}

interface FormFieldProps {
  id: string
  label: string
  hint?: string
  error?: string
  children: (control: FieldControlProps) => ReactNode
}

// Visible label above, hint and error below, all linked to the control
export function FormField({
  id,
  label,
  hint,
  error,
  children,
}: FormFieldProps) {
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') ||
    undefined

  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className="text-sm font-medium">
        {label}
      </label>
      {children({
        id,
        'aria-describedby': describedBy,
        'aria-invalid': error ? true : undefined,
      })}
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
      {error && (
        <p id={errorId} className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  )
}
