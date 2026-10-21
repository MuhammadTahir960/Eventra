import { describe, expect, it } from 'vitest'
import { decideReconnect, reconnectDelay } from './socket-policy'

describe('decideReconnect', () => {
  it('gives up when the event is not visible', () => {
    expect(decideReconnect(4404)).toBe('stop')
  })

  it('backs off hard when rate limited', () => {
    expect(decideReconnect(4429)).toBe('slow')
  })

  it.each([4401, 4400, 1006, 1001, 1012])('retries after code %i', (code) => {
    expect(decideReconnect(code)).toBe('retry')
  })
})

describe('reconnectDelay', () => {
  const noJitter = () => 0
  const fullJitter = () => 1

  it('doubles each attempt', () => {
    expect(reconnectDelay(0, 'retry', noJitter)).toBe(1_000)
    expect(reconnectDelay(1, 'retry', noJitter)).toBe(2_000)
    expect(reconnectDelay(2, 'retry', noJitter)).toBe(4_000)
  })

  it('never exceeds the cap (plus jitter)', () => {
    expect(reconnectDelay(20, 'retry', noJitter)).toBe(15_000)
    expect(reconnectDelay(20, 'retry', fullJitter)).toBe(18_750)
  })

  it('waits much longer when rate limited', () => {
    expect(reconnectDelay(0, 'slow', noJitter)).toBe(30_000)
  })

  it('adds up to 25% jitter', () => {
    expect(reconnectDelay(0, 'retry', fullJitter)).toBe(1_250)
  })
})
