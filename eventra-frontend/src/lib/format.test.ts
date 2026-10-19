import { describe, expect, it } from 'vitest'
import { isUuid } from './ids'
import { formatMoney } from './format'

describe('formatMoney', () => {
  it('formats decimal strings from the API as USD', () => {
    expect(formatMoney('45.00')).toBe('$45.00')
    expect(formatMoney('1234.5')).toBe('$1,234.50')
  })

  it('shows a dash for values that are not numbers', () => {
    expect(formatMoney('abc')).toBe('—')
  })
})

describe('isUuid', () => {
  it('accepts a UUID', () => {
    expect(isUuid('3f0c1a2e-8b7d-4c6e-9a10-5d2b7c9e4f11')).toBe(true)
  })

  it.each(['', 'not-a-uuid', '../etc/passwd', undefined, null])(
    'rejects %s',
    (value) => {
      expect(isUuid(value)).toBe(false)
    },
  )
})
