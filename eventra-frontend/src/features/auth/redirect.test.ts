import { describe, expect, it } from 'vitest'
import { safeRedirect } from './redirect'

describe('safeRedirect', () => {
  it('allows same-site paths', () => {
    expect(safeRedirect('/events/derby/seats')).toBe('/events/derby/seats')
  })

  it.each([
    'https://evil.example',
    '//evil.example',
    '/\\evil.example',
    'events',
    '',
    undefined,
    42,
  ])('rejects %s', (value) => {
    expect(safeRedirect(value)).toBeNull()
  })
})
