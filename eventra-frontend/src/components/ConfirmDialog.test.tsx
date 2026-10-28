import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { Button } from '@/components/ui/button'
import { ConfirmDialog } from './ConfirmDialog'

function dialog(onConfirm: () => void, pending = false) {
  return (
    <ConfirmDialog
      open
      onOpenChange={() => {}}
      trigger={<Button>Open</Button>}
      title="Pay out this event?"
      description="Pays the organizer."
      confirmLabel="Pay out"
      pending={pending}
      onConfirm={onConfirm}
    />
  )
}

describe('ConfirmDialog', () => {
  it('runs the action once on a double click', () => {
    const onConfirm = vi.fn()
    render(dialog(onConfirm))
    const confirm = screen.getByRole('button', { name: 'Pay out' })
    fireEvent.click(confirm)
    fireEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('can be confirmed again once the action has finished', () => {
    const onConfirm = vi.fn()
    const { rerender } = render(dialog(onConfirm))
    fireEvent.click(screen.getByRole('button', { name: 'Pay out' }))
    rerender(dialog(onConfirm, true))
    rerender(dialog(onConfirm, false))
    fireEvent.click(screen.getByRole('button', { name: 'Pay out' }))
    expect(onConfirm).toHaveBeenCalledTimes(2)
  })
})
