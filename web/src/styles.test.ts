/**
 * The stylesheet rules that can break a page without looking wrong in review.
 *
 * A hover rule that takes its element out of the layout is the whole reason this file
 * exists. `a.card:hover` once set `position: absolute` and a 1px box — the body of
 * `.visually-hidden`, pasted in with its selector fused to the one above it. Hovering a
 * group card made it disappear, the list jumped up under the cursor, the cursor was then off
 * the card, the card came back: a flicker loop that also swallowed clicks meant for the card
 * below, since an absolutely positioned element covers what follows it.
 *
 * Nothing about that is visible until a pointer touches the page, which is why it shipped
 * with the web app and survived every visual pass after it. A regression test for exactly
 * that one selector would be worth little; the class of mistake is worth catching.
 */

import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

const css = readFileSync(new URL('./styles.css', import.meta.url), 'utf8')

interface Rule {
  selector: string
  body: string
}

/** Every top-level rule, flattened enough for this. Not a parser — a reader. */
function rules(): Rule[] {
  const found: Rule[] = []
  const pattern = /([^{}]+)\{([^{}]*)\}/g
  let match: RegExpExecArray | null
  while ((match = pattern.exec(css)) !== null) {
    const [, rawSelector = '', body = ''] = match
    const selector = rawSelector.replace(/\/\*[\s\S]*?\*\//g, '').trim()
    if (selector && !selector.startsWith('@')) {
      found.push({ selector, body })
    }
  }
  return found
}

/**
 * Properties that move an element out of, or resize it within, the normal flow.
 *
 * Changing any of these on hover means the pointer can end up somewhere else than where it
 * started, and the browser will re-evaluate the hover — sometimes forever.
 */
const DISPLACING = ['position', 'display', 'width', 'height', 'float', 'clip-path']

describe('hover rules', () => {
  const hovers = rules().filter((rule) => rule.selector.includes(':hover'))

  it('there are some, or this file is checking nothing', () => {
    expect(hovers.length).toBeGreaterThan(0)
  })

  it.each(DISPLACING)('never change %s', (property) => {
    const offenders = hovers
      .filter((rule) => new RegExp(`(^|[;\\s])${property}\\s*:`).test(rule.body))
      .map((rule) => rule.selector)

    expect(offenders).toEqual([])
  })
})

describe('the screen-reader helper', () => {
  /**
   * It is applied to a table heading, so if the rule stops matching, the word "Place"
   * appears in the standings header and nobody understands why.
   */
  it('is defined on its own, not welded to some other selector', () => {
    const defined = rules().filter((rule) => rule.selector === '.visually-hidden')

    expect(defined).toHaveLength(1)
    expect(defined[0]?.body).toContain('clip-path')
  })
})
