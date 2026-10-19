import { describe, expect, it } from 'vitest'
import { initial } from './initial'

describe('initial', () => {
  it.each([
    ['Harbor Lights', 'H'],
    ['dana', 'D'],
    ['🎷 Late Jazz', 'L'],
    ['#SummerSound', 'S'],
    ['Đêm Nhạc', 'Đ'],
    ['  Ólafur', 'Ó'],
    ['王秀英', '王'],
  ])('%j -> %j', (text, expected) => {
    expect(initial(text)).toBe(expected)
  })

  it('falls back when there is no letter at all', () => {
    expect(initial('🦊')).toBe('?')
    expect(initial('', '')).toBe('')
  })
})
