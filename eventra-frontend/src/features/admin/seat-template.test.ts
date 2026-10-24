import { describe, expect, it } from 'vitest'
import {
  buildTemplate,
  parseRowLabels,
  type SectionDraft,
} from './seat-template'

describe('parseRowLabels', () => {
  it.each([
    ['A-D', ['A', 'B', 'C', 'D']],
    ['a - c', ['A', 'B', 'C']],
    ['1-3', ['1', '2', '3']],
    ['AA, BB', ['AA', 'BB']],
    ['A-B, B, C', ['A', 'B', 'C']],
  ])('reads %j', (input, expected) => {
    expect(parseRowLabels(input)).toEqual(expected)
  })

  it.each(['', 'D-A', 'A-3', 'A-B-C', 'TOOLONGLABEL', '<b>', '1-500'])(
    'rejects %j',
    (input) => {
      expect(parseRowLabels(input)).toBeNull()
    },
  )
})

const section = (overrides: Partial<SectionDraft> = {}): SectionDraft => ({
  key: 's1',
  name: 'Stalls',
  rows: 'A-C',
  seatsPerRow: '10',
  ...overrides,
})

describe('buildTemplate', () => {
  it('builds the payload and counts seats', () => {
    const result = buildTemplate(
      [
        section(),
        section({ key: 's2', name: 'Circle', rows: '1-2', seatsPerRow: '5' }),
      ],
      100,
    )
    expect(result.errors).toEqual({})
    expect(result.total).toBe(40)
    expect(result.payload?.sections[1]).toEqual({
      name: 'Circle',
      rows: [
        { row_label: '1', seat_count: 5 },
        { row_label: '2', seat_count: 5 },
      ],
    })
  })

  it('refuses more seats than the venue holds', () => {
    const result = buildTemplate([section()], 20)
    expect(result.payload).toBeNull()
    expect(result.errors.total).toMatch(/capacity of 20/)
  })

  it('flags duplicate section names and bad seat counts', () => {
    const result = buildTemplate(
      [section(), section({ key: 's2', name: 'stalls', seatsPerRow: '0' })],
      1000,
    )
    expect(result.errors['s2-name']).toBeDefined()
    expect(result.errors['s2-seats']).toBeDefined()
  })
})
