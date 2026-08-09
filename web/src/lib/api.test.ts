/**
 * The one piece of logic on this side of the wire that also exists on the other.
 *
 * `canScore` decides which courts get a score box; `require_can_score` in
 * `services/permissions.py` decides which ones the server will accept. They must agree —
 * a box that 403s is worse than no box — and the only thing standing between them is that
 * both were written from the same four branches. These pin this side of it, branch for
 * branch, in the same order the server reads them.
 */

import { describe, expect, it } from 'vitest'

import type { Match, Viewer } from './api'
import { canScore } from './api'

const ANYA = '01980000-0000-7000-8000-000000000001'
const BORYA = '01980000-0000-7000-8000-000000000002'
const VIKA = '01980000-0000-7000-8000-000000000003'
const GRISHA = '01980000-0000-7000-8000-000000000004'
const ELSEWHERE = '01980000-0000-7000-8000-00000000000f'

const match: Match = {
  court: 1,
  team_a: ['Аня', 'Боря'],
  team_b: ['Вика', 'Гриша'],
  score_a: null,
  score_b: null,
  team_a_ids: [ANYA, BORYA],
  team_b_ids: [VIKA, GRISHA],
}

function viewer(overrides: Partial<Viewer> = {}): Viewer {
  return {
    is_member: true,
    is_organiser: false,
    plays_as: null,
    anyone_may_score: false,
    ...overrides,
  }
}

describe('canScore', () => {
  it('refuses somebody who is not in the group at all', () => {
    expect(canScore(viewer({ is_member: false }), match)).toBe(false)
  })

  it('lets the organiser score any court', () => {
    expect(canScore(viewer({ is_organiser: true, plays_as: ELSEWHERE }), match)).toBe(true)
  })

  it('lets any member score when nobody organises', () => {
    expect(canScore(viewer({ anyone_may_score: true, plays_as: ELSEWHERE }), match)).toBe(true)
  })

  it('lets a member who has claimed no player score, because we cannot tell them apart', () => {
    expect(canScore(viewer({ plays_as: null }), match)).toBe(true)
  })

  it('lets somebody score the court they played on', () => {
    expect(canScore(viewer({ plays_as: VIKA }), match)).toBe(true)
  })

  it('refuses a known player who was on another court', () => {
    expect(canScore(viewer({ plays_as: ELSEWHERE }), match)).toBe(false)
  })
})
