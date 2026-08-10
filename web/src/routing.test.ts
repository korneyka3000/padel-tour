/**
 * The one thing about the SPA rewrite that can be wrong without anybody noticing.
 *
 * Everything that is not `/api/` is rewritten to `index.html`, which is what makes a deep
 * link like `/t/<uuid>` work on a refresh. It also catches paths that were never pages —
 * the analytics beacon posts to `/_vercel/insights/*`, and without an exclusion that gets
 * `index.html` back: a 200, nothing in the console, and no data, ever.
 *
 * The config is read rather than duplicated, because a copy of a rule is a second rule.
 */

import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

interface Rewrite {
  source: string
  destination: string
}

const config = JSON.parse(
  readFileSync(new URL('../../vercel.json', import.meta.url), 'utf8'),
) as { rewrites: Rewrite[] }

const catchAll = config.rewrites.find((rule) => rule.destination === '/index.html')

describe('the SPA rewrite', () => {
  it('is there at all', () => {
    expect(catchAll).toBeDefined()
  })

  it('leaves the platform and the API alone', () => {
    const pattern = new RegExp(`^${catchAll?.source ?? ''}$`)

    expect(pattern.test('/_vercel/insights/view')).toBe(false)
    expect(pattern.test('/api/health')).toBe(false)
  })

  it('still sends every real page to the app', () => {
    const pattern = new RegExp(`^${catchAll?.source ?? ''}$`)

    expect(pattern.test('/')).toBe(true)
    expect(pattern.test('/t/019fed76-5a59-7756-bb84-f7fbc06049f6')).toBe(true)
    expect(pattern.test('/g/019fed76-5a59-7756-bb84-f7fbc06049f6/play')).toBe(true)
    expect(pattern.test('/auth/enter')).toBe(true)
  })
})
