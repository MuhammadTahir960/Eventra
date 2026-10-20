import { describe, expect, it } from 'vitest'
import { isUuid, pageParam } from './ids'

describe('pageParam', () => {
  it.each([
    [null, 1],
    ['', 1],
    ['2', 2],
    ['26', 26],
    ['0', 1],
    ['-3', 1],
    ['2.5', 1],
    ['abc', 1],
  ])('%j -> %j', (value, expected) => {
    expect(pageParam(value)).toBe(expected)
  })
})

describe('isUuid', () => {
  it('accepts a UUID and rejects anything else', () => {
    expect(isUuid('3f0c1a2e-8b7d-4c6e-9a10-5d2b7c9e4f11')).toBe(true)
    expect(isUuid('../admin')).toBe(false)
    expect(isUuid(null)).toBe(false)
  })
})
