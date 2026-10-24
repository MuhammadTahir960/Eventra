import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { LayoutSeatInput } from '../layout/layout'
import { VenueMapPreview } from './VenueMapPreview'

function makeSeats(): LayoutSeatInput[] {
  const seats: LayoutSeatInput[] = []
  for (const section of ['VIP', 'Business', 'Economy']) {
    for (const row of ['A', 'B']) {
      for (let n = 1; n <= 6; n += 1) {
        seats.push({
          id: `${section}-${row}-${n}`,
          section,
          row_label: row,
          seat_number: n,
        })
      }
    }
  }
  return seats
}

describe('VenueMapPreview', () => {
  it('draws one dot per seat and describes the venue', () => {
    const { container } = render(
      <VenueMapPreview seats={makeSeats()} shape="circle" />,
    )

    const map = screen.getByRole('img')
    expect(map).toHaveAccessibleName(
      'Top-down map of a circular venue with 36 seats in 3 sections',
    )
    expect(container.querySelectorAll('circle')).toHaveLength(36)
  })

  it('lists every section in an accessible table', () => {
    render(<VenueMapPreview seats={makeSeats()} shape="oval" />)

    const table = screen.getByRole('table', { name: 'Sections in this venue' })
    const rows = within(table).getAllByRole('row')
    // Header + one row per section
    expect(rows).toHaveLength(4)
    expect(within(table).getByRole('rowheader', { name: 'VIP' })).toBeVisible()
  })

  it('falls back to an oval for a shape it does not know', () => {
    render(<VenueMapPreview seats={makeSeats()} shape="hexagon" />)
    expect(screen.getByRole('img')).toHaveAccessibleName(
      expect.stringContaining('oval venue'),
    )
  })

  it('describes a U-shaped venue as U-shaped', () => {
    render(<VenueMapPreview seats={makeSeats()} shape="u_shape" />)
    expect(screen.getByRole('img')).toHaveAccessibleName(
      expect.stringContaining('U-shaped venue'),
    )
  })

  describe('when sections are selectable', () => {
    it('reports clicks and announces tier hints', () => {
      const onSelect = vi.fn()
      render(
        <VenueMapPreview
          seats={makeSeats()}
          shape="oval"
          onSectionSelect={onSelect}
          sectionHints={{ VIP: 'Gold tier' }}
        />,
      )

      // No longer a plain image, because it now contains buttons
      expect(screen.queryByRole('img')).not.toBeInTheDocument()
      const vip = screen.getByRole('button', { name: 'Section VIP, Gold tier' })
      fireEvent.click(vip)
      expect(onSelect).toHaveBeenCalledWith('VIP')
    })

    it('works from the keyboard', () => {
      const onSelect = vi.fn()
      render(
        <VenueMapPreview
          seats={makeSeats()}
          shape="oval"
          onSectionSelect={onSelect}
        />,
      )

      const economy = screen.getByRole('button', { name: 'Section Economy' })
      fireEvent.keyDown(economy, { key: 'Enter' })
      fireEvent.keyDown(economy, { key: ' ' })
      fireEvent.keyDown(economy, { key: 'a' })
      expect(onSelect).toHaveBeenCalledTimes(2)
    })
  })
})
