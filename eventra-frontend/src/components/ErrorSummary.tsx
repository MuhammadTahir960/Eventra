import { useEffect, useRef } from 'react'

export interface ErrorItem {
  fieldId: string
  message: string
}

// Shown above a form after a failed submit. It takes focus so screen reader
// users hear the problems, and each item jumps to its field.
export function ErrorSummary({
  errors,
  focusKey,
}: {
  errors: ErrorItem[]
  // Increment on each failed submit to move focus here again
  focusKey: number
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (focusKey > 0) ref.current?.focus()
  }, [focusKey])

  if (errors.length === 0) return null

  return (
    <div
      ref={ref}
      tabIndex={-1}
      role="alert"
      className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm outline-none"
    >
      <p className="font-medium text-destructive">
        Please fix {errors.length === 1 ? 'this problem' : 'these problems'}:
      </p>
      <ul className="mt-1 list-disc space-y-0.5 pl-5">
        {errors.map((item) => (
          <li key={`${item.fieldId}-${item.message}`}>
            <a
              href={`#${item.fieldId}`}
              className="underline underline-offset-2"
              onClick={(event) => {
                event.preventDefault()
                document.getElementById(item.fieldId)?.focus()
              }}
            >
              {item.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}
