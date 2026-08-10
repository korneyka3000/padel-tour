/**
 * Where a launch goes.
 *
 * `?startapp=` is the only thing Telegram passes through, so destinations are encoded into
 * it. A malformed one has to land somewhere sensible rather than on a broken route — the
 * value comes from a chat message, and chat messages get edited by hand.
 */

import { describe, expect, it } from 'vitest'

import { launchDestination } from './telegram'

const ID = '019fed76-5a59-7756-bb84-f7fbc06049f6'

describe('launchDestination', () => {
  it('opens a tournament', () => {
    expect(launchDestination(`t_${ID}`)).toBe(`/t/${ID}`)
  })

  it('opens a group', () => {
    expect(launchDestination(`g_${ID}`)).toBe(`/g/${ID}`)
  })

  it('falls back home when there is no parameter', () => {
    expect(launchDestination(undefined)).toBe('/')
    expect(launchDestination('')).toBe('/')
  })

  it('falls back home rather than routing to nonsense', () => {
    expect(launchDestination('nonsense')).toBe('/')
    expect(launchDestination('t_')).toBe('/')
    expect(launchDestination('x_' + ID)).toBe('/')
  })
})
