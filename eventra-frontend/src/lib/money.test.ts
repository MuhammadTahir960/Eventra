import { describe, expect, it } from 'vitest'
import { sumPrices, toCents } from './money'

describe('toCents', () => {
  it.each([
    ['45.00', 4500],
    ['45', 4500],
    ['0.05', 5],
    ['0.5', 50],
    ['1234.56', 123456],
  ])('converts %s', (price, cents) => {
    expect(toCents(price)).toBe(cents)
  })

  it.each(['', 'abc', '-5', '1.234', '1,50'])('rejects %j', (price) => {
    expect(toCents(price)).toBeNaN()
  })

  // The seat map endpoint sends prices as JSON numbers
  it.each([
    [45, 4500],
    [45.5, 4550],
    [0.1 + 0.2, 30],
  ])('converts the number %s', (price, cents) => {
    expect(toCents(price)).toBe(cents)
  })

  it.each([-5, Number.NaN, Infinity])('rejects the number %s', (price) => {
    expect(toCents(price)).toBeNaN()
  })
})

describe('sumPrices', () => {
  it('adds number and string prices alike', () => {
    expect(sumPrices([45, '28.00', 0.1])).toBe('73.10')
  })

  it('adds without floating point drift', () => {
    // 0.1 + 0.2 is 0.30000000000000004 as plain numbers
    expect(sumPrices(['0.10', '0.20'])).toBe('0.30')
  })

  it('adds seat prices across tiers', () => {
    expect(sumPrices(['120.00', '40.00', '40.00'])).toBe('200.00')
  })

  it('pads cents', () => {
    expect(sumPrices(['10.05', '0.00'])).toBe('10.05')
  })

  it('is zero for no seats', () => {
    expect(sumPrices([])).toBe('0.00')
  })

  it('falls back to zero if a price is malformed', () => {
    expect(sumPrices(['10.00', 'oops'])).toBe('0.00')
  })
})
