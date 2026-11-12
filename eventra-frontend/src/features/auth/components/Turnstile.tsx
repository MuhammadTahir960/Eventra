import { useEffect, useRef } from 'react'
import { TURNSTILE_SITE_KEY } from '@/lib/config'

interface TurnstileApi {
  render(
    element: HTMLElement,
    options: {
      sitekey: string
      callback: (token: string) => void
      'expired-callback': () => void
      'error-callback': () => void
    },
  ): string
  remove(widgetId: string): void
}

declare global {
  interface Window {
    turnstile?: TurnstileApi
  }
}

const SCRIPT_URL =
  'https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit'
let scriptLoading: Promise<void> | null = null

function loadScript(): Promise<void> {
  scriptLoading ??= new Promise((resolve, reject) => {
    const script = document.createElement('script')
    script.src = SCRIPT_URL
    script.async = true
    script.onload = () => resolve()
    script.onerror = () => {
      scriptLoading = null
      reject(new Error('Turnstile could not load'))
    }
    document.head.append(script)
  })
  return scriptLoading
}

// Cloudflare's "are you human" check. Tokens are single use, so the caller
// bumps `resetKey` after every submit to get a fresh one.
export function Turnstile({
  onToken,
  resetKey,
}: {
  onToken: (token: string | null) => void
  resetKey: number
}) {
  const box = useRef<HTMLDivElement>(null)
  const latest = useRef(onToken)
  useEffect(() => {
    latest.current = onToken
  })

  useEffect(() => {
    let widgetId: string | undefined
    let cancelled = false
    latest.current(null)
    loadScript()
      .then(() => {
        if (cancelled || !box.current || !window.turnstile) return
        widgetId = window.turnstile.render(box.current, {
          sitekey: TURNSTILE_SITE_KEY,
          callback: (token) => latest.current(token),
          'expired-callback': () => latest.current(null),
          'error-callback': () => latest.current(null),
        })
      })
      .catch(() => latest.current(null))
    return () => {
      cancelled = true
      if (widgetId) window.turnstile?.remove(widgetId)
    }
  }, [resetKey])

  return <div ref={box} className="min-h-[65px]" />
}
