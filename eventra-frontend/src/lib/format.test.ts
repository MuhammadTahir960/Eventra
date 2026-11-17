import { describe, expect, it } from 'vitest'
import { isUuid } from './ids'
import {
  countryName,
  formatDateTime,
  formatDateTimeLong,
  formatMoney,
  toLocalInput,
} from './format'

describe('formatMoney', () => {
  it('formats decimal strings from the API as USD', () => {
    expect(formatMoney('45.00')).toBe('$45.00')
    expect(formatMoney('1234.5')).toBe('$1,234.50')
  })

  it('shows a dash for values that are not numbers', () => {
    expect(formatMoney('abc')).toBe('—')
  })
})

describe('event times', () => {
  // 13:30 UTC is 18:30 in Karachi (UTC+5) and 08:30 in New York (winter)
  const iso = '2027-01-10T13:30:00Z'

  it("are shown on the venue's clock, whatever the viewer's zone", () => {
    expect(formatDateTime(iso, 'Asia/Karachi')).toContain('6:30')
    expect(formatDateTime(iso, 'America/New_York')).toContain('8:30')
    expect(formatDateTimeLong(iso, 'Asia/Karachi')).toMatch(/GMT\+5|PKT/)
  })

  it("fill a datetime-local input with the venue's wall-clock time", () => {
    expect(toLocalInput(iso, 'Asia/Karachi')).toBe('2027-01-10T18:30')
    expect(toLocalInput(iso, 'America/New_York')).toBe('2027-01-10T08:30')
    // midnight is 00, not 24
    expect(toLocalInput('2027-01-10T19:00:00Z', 'Asia/Karachi')).toBe(
      '2027-01-11T00:00',
    )
  })
})

describe('countryName', () => {
  it('names an ISO country code', () => {
    expect(countryName('PK')).toBe('Pakistan')
    expect(countryName('GB')).toBe('United Kingdom')
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
