import { act, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { Turnstile } from './Turnstile'

describe('Turnstile', () => {
  afterEach(() => {
    delete window.turnstile
  })

  it('renders a fresh check per resetKey and passes tokens up', async () => {
    let callback: ((token: string) => void) | undefined
    const turnstile = {
      render: vi.fn((_el, options) => {
        callback = options.callback
        return `widget-${turnstile.render.mock.calls.length}`
      }),
      remove: vi.fn(),
    }
    const onToken = vi.fn()
    const { rerender } = render(<Turnstile onToken={onToken} resetKey={0} />)

    // The page loads Cloudflare's script once; pretend it arrived
    window.turnstile = turnstile
    const script = document.head.querySelector<HTMLScriptElement>(
      'script[src*="challenges.cloudflare.com"]',
    )
    await act(async () => script?.onload?.(new Event('load')))
    expect(turnstile.render).toHaveBeenCalledTimes(1)

    act(() => callback?.('token-1'))
    expect(onToken).toHaveBeenLastCalledWith('token-1')

    // A new attempt clears the old token and asks for a new check
    await act(async () =>
      rerender(<Turnstile onToken={onToken} resetKey={1} />),
    )
    expect(turnstile.remove).toHaveBeenCalledWith('widget-1')
    expect(onToken).toHaveBeenLastCalledWith(null)
    expect(turnstile.render).toHaveBeenCalledTimes(2)
  })
})
