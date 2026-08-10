/**
 * The dictionary, and the parts of it a type cannot check.
 *
 * TypeScript already guarantees that `en` has every key `ru` does. What it cannot see is
 * whether the placeholders inside a phrase match between the two — swap `{name}` for
 * `{who}` in one language and that language quietly renders the braces.
 */

import { describe, expect, it } from 'vitest'

import { en, preferredLocale, ru, translator } from './i18n'
import type { Key } from './i18n'

const say = (failure: unknown) => (failure instanceof Error ? failure.message : 'unknown')

function placeholders(phrase: string): string[] {
  return [...phrase.matchAll(/\{(\w+)\}/g)].map((found) => found[1] ?? '').sort()
}

describe('the dictionaries', () => {
  it('agree on which values each phrase expects', () => {
    const disagreeing = (Object.keys(ru) as Key[]).filter(
      (key) => placeholders(ru[key]).join() !== placeholders(en[key]).join(),
    )

    expect(disagreeing).toEqual([])
  })

  it('leave no phrase empty', () => {
    const blank = (Object.keys(ru) as Key[]).filter(
      (key) => ru[key].trim() === '' || en[key].trim() === '',
    )

    expect(blank).toEqual([])
  })
})

describe('counting', () => {
  it('picks the Russian category, of which there are three', () => {
    const t = translator('ru', say)

    expect(t.count('players', 1)).toBe('1 игрок')
    expect(t.count('players', 3)).toBe('3 игрока')
    expect(t.count('players', 8)).toBe('8 игроков')
    // The teens exception, which is where a hand-rolled rule usually goes wrong.
    expect(t.count('players', 11)).toBe('11 игроков')
    expect(t.count('players', 21)).toBe('21 игрок')
  })

  it('picks the English one, of which there are two', () => {
    const t = translator('en', say)

    expect(t.count('players', 1)).toBe('1 player')
    expect(t.count('players', 3)).toBe('3 players')
  })
})

describe('choosing a language', () => {
  it('honours a stored choice above anything the browser says', () => {
    expect(preferredLocale('en', 'ru-RU')).toBe('en')
    expect(preferredLocale('ru', 'en-GB')).toBe('ru')
  })

  it('falls back to the browser, then to Russian', () => {
    expect(preferredLocale(null, 'en-US')).toBe('en')
    expect(preferredLocale(null, 'ru-RU')).toBe('ru')
    expect(preferredLocale(null, 'fr-FR')).toBe('ru')
  })

  it('ignores a stored value that is not a language we have', () => {
    expect(preferredLocale('klingon', 'en-US')).toBe('en')
  })
})
