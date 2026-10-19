import { useState, type ComponentProps, type ReactNode } from 'react'

// An <img> that shows `fallback` instead of the broken-image icon when the
// file is missing (a deleted upload, a dead storage URL).
export function ImageWithFallback({
  fallback,
  ...props
}: ComponentProps<'img'> & { fallback: ReactNode }) {
  const [failedSrc, setFailedSrc] = useState<string | undefined>()
  // Keyed by src, so a new image gets a fresh try
  if (props.src && failedSrc === props.src) return <>{fallback}</>
  return <img {...props} onError={() => setFailedSrc(props.src)} />
}
