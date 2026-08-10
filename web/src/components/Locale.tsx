/**
 * Which language the page speaks, and the one function everything else uses to speak it.
 *
 * The choice is remembered in `localStorage` rather than in the account: it belongs to the
 * device you are holding, and a phone in a Russian kitchen and a laptop in an English
 * office can reasonably disagree.
 */

import { createContext, useCallback, useContext, useMemo, useState } from 'react'

import { ApiError } from '../lib/api'
import type { Key, Locale, Translate } from '../lib/i18n'
import { DICTIONARIES, isLocale, preferredLocale, translator } from '../lib/i18n'
import { telegramLanguage } from '../lib/telegram'

const STORAGE_KEY = 'pt_locale'

interface Chosen {
  t: Translate
  locale: Locale
  choose: (locale: Locale) => void
}

const LocaleContext = createContext<Chosen | null>(null)

function stored(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    // Safari in private mode throws on localStorage. A language preference is not worth
    // taking the page down for.
    return null
  }
}

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  // Telegram's own setting first, because inside Telegram that is the language the person
  // has already chosen for everything else. A stored choice still beats it — see below.
  const [locale, setLocale] = useState<Locale>(() =>
    preferredLocale(stored(), telegramLanguage() ?? navigator.language),
  )

  const choose = useCallback((next: Locale) => {
    setLocale(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // See above: the choice still applies to this page, it just will not outlive it.
    }
  }, [])

  const value = useMemo<Chosen>(() => {
    const words = DICTIONARIES[locale]

    /**
     * A failure, said in this language.
     *
     * By code, never by matching the English sentence — that would break the first time
     * somebody reworded it. An unknown code falls through to whatever the server said,
     * because an old page against a new server should show an awkward sentence rather than
     * an empty one.
     */
    const say = (failure: unknown): string => {
      if (failure instanceof ApiError && failure.code) {
        const phrase = words[`error.${failure.code}` as Key] as string | undefined
        if (phrase) {
          return phrase.replace(/\{(\w+)\}/g, (whole, name: string) => {
            const given = failure.params[name]
            return given === undefined ? whole : String(given)
          })
        }
      }
      if (failure instanceof Error) return failure.message
      return words['async.somethingWrong']
    }

    return { t: translator(locale, say), locale, choose }
  }, [locale, choose])

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>
}

function chosen(): Chosen {
  const value = useContext(LocaleContext)
  if (value === null) throw new Error('LocaleProvider is missing above this component')
  return value
}

/** The translator. What almost every component wants. */
export function useT(): Translate {
  return chosen().t
}

/** For the switcher, which is the only thing that needs to change the language. */
export function useLocaleChoice(): { locale: Locale; choose: (locale: Locale) => void } {
  const { locale, choose } = chosen()
  return { locale, choose }
}

export { isLocale }
