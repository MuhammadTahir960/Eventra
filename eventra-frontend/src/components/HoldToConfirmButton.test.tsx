import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { HoldToConfirmButton } from './HoldToConfirmButton'

function setup() {
  const onConfirm = vi.fn()
  render(
    <HoldToConfirmButton
      label="Hold to cancel event"
      confirmedLabel="Cancelling…"
      durationMs={1600}
      onConfirm={onConfirm}
    />,
  )
  return { onConfirm, button: screen.getByRole('button') }
}

describe('HoldToConfirmButton', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('confirms only after the full hold', () => {
    const { onConfirm, button } = setup()
    fireEvent.pointerDown(button, { button: 0, pointerId: 1 })
    act(() => vi.advanceTimersByTime(1599))
    expect(onConfirm).not.toHaveBeenCalled()
    act(() => vi.advanceTimersByTime(1))
    expect(onConfirm).toHaveBeenCalledOnce()
    expect(button).toHaveTextContent('Cancelling…')
  })

  it('does nothing when released early, and a plain click never fires it', () => {
    const { onConfirm, button } = setup()
    fireEvent.pointerDown(button, { button: 0, pointerId: 1 })
    act(() => vi.advanceTimersByTime(800))
    fireEvent.pointerUp(button, { pointerId: 1 })
    act(() => vi.advanceTimersByTime(2000))
    fireEvent.click(button)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('works by holding Enter or Space, and ignores key repeat', () => {
    const { onConfirm, button } = setup()
    fireEvent.keyDown(button, { key: ' ' })
    fireEvent.keyDown(button, { key: ' ', repeat: true })
    act(() => vi.advanceTimersByTime(1600))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('cancels when focus leaves mid-hold', () => {
    const { onConfirm, button } = setup()
    fireEvent.keyDown(button, { key: 'Enter' })
    fireEvent.blur(button)
    act(() => vi.advanceTimersByTime(2000))
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
