import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { EventSeat, SeatStatus } from '../types'
import { SeatMap } from './SeatMap'

function makeSeats(statusOf: (id: string) => SeatStatus = () => 'available') {
  const seats: EventSeat[] = []
  for (const [section, tier, price] of [
    ['VIP', 'tier-vip', '120.00'],
    ['Economy', 'tier-eco', '40.00'],
  ] as const) {
    for (const row of ['A', 'B']) {
      for (let n = 1; n <= 4; n += 1) {
        const id = `${section}-${row}${n}`
        seats.push({
          id,
          section,
          row_label: row,
          seat_number: n,
          ticket_tier: tier,
          tier_name: section,
          price,
          status: statusOf(id),
        })
      }
    }
  }
  return seats
}

const seatButton = (label: RegExp | string) =>
  screen.getByRole('button', { name: label })

describe('SeatMap', () => {
  it('draws every seat as a labelled button', () => {
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={() => {}}
      />,
    )
    expect(
      seatButton('Section VIP, row A, seat 1, VIP, $120.00, available'),
    ).toBeInTheDocument()
    expect(
      screen.getAllByRole('button', { name: /Section .*, row .*, seat / }),
    ).toHaveLength(16)
  })

  it('selects an available seat when clicked', () => {
    const onToggle = vi.fn()
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={onToggle}
      />,
    )
    fireEvent.click(seatButton(/Section VIP, row A, seat 2/))
    expect(onToggle).toHaveBeenCalledWith('VIP-A2')
  })

  it('shows selected seats as pressed', () => {
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set(['VIP-A2'])}
        onToggle={() => {}}
      />,
    )
    const seat = seatButton(/Section VIP, row A, seat 2/)
    expect(seat).toHaveAttribute('aria-pressed', 'true')
    expect(seat).toHaveAccessibleName(expect.stringContaining('selected'))
  })

  it('does not let anyone pick held or sold seats', () => {
    const onToggle = vi.fn()
    render(
      <SeatMap
        seats={makeSeats((id) =>
          id === 'VIP-A1' ? 'held' : id === 'VIP-A2' ? 'booked' : 'available',
        )}
        shape="oval"
        selected={new Set()}
        onToggle={onToggle}
      />,
    )
    const held = seatButton(/Section VIP, row A, seat 1/)
    const sold = seatButton(/Section VIP, row A, seat 2/)
    expect(held).toHaveAccessibleName(
      expect.stringContaining('held by another buyer'),
    )
    expect(sold).toHaveAccessibleName(expect.stringContaining('sold'))
    expect(held).toHaveAttribute('aria-disabled', 'true')

    fireEvent.click(held)
    fireEvent.click(sold)
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('ignores clicks while a request is in progress', () => {
    const onToggle = vi.fn()
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={onToggle}
        disabled
      />,
    )
    fireEvent.click(seatButton(/Section VIP, row A, seat 1/))
    expect(onToggle).not.toHaveBeenCalled()
  })

  it('selects with Enter and Space from the keyboard', () => {
    const onToggle = vi.fn()
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={onToggle}
      />,
    )
    const seat = seatButton(/Section VIP, row A, seat 1/)
    fireEvent.keyDown(seat, { key: 'Enter' })
    fireEvent.keyDown(seat, { key: ' ' })
    expect(onToggle).toHaveBeenCalledTimes(2)
  })

  it('has one tab stop, and arrow keys move it', () => {
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={() => {}}
      />,
    )
    const allSeats = () =>
      screen.getAllByRole('button', { name: /Section .*, row .*, seat / })

    // Exactly one seat is reachable with Tab
    expect(
      allSeats().filter((s) => s.getAttribute('tabindex') === '0'),
    ).toHaveLength(1)

    const first = seatButton(/Section Economy, row A, seat 1/)
    expect(first).toHaveAttribute('tabindex', '0')

    fireEvent.keyDown(first, { key: 'ArrowRight' })
    expect(seatButton(/Section Economy, row A, seat 2/)).toHaveAttribute(
      'tabindex',
      '0',
    )
    expect(first).toHaveAttribute('tabindex', '-1')
    expect(
      allSeats().filter((s) => s.getAttribute('tabindex') === '0'),
    ).toHaveLength(1)
  })

  it('lists the ticket tiers with their prices', () => {
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={() => {}}
      />,
    )
    const legend = screen.getByRole('list', { name: 'Ticket tiers' })
    expect(legend).toHaveTextContent('Economy')
    expect(legend).toHaveTextContent('$40.00')
    expect(legend).toHaveTextContent('VIP')
    expect(legend).toHaveTextContent('$120.00')
  })

  it('lets people zoom to a section and back', () => {
    render(
      <SeatMap
        seats={makeSeats()}
        shape="oval"
        selected={new Set()}
        onToggle={() => {}}
      />,
    )
    const whole = screen.getByRole('button', { name: 'Whole venue' })
    expect(whole).toBeDisabled()

    fireEvent.change(screen.getByLabelText('Zoom to section'), {
      target: { value: 'VIP' },
    })
    expect(whole).toBeEnabled()
    fireEvent.click(whole)
    expect(whole).toBeDisabled()
  })
})
