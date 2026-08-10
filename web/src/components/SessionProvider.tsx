/** Asks the server who is signed in, once, and tells the rest of the app. */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, api, type Me } from '../lib/api'
import { SessionContext } from '../lib/auth'
import { insideTelegram, settle, webApp } from '../lib/telegram'

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      setMe(await api.me())
    } catch (error) {
      // 401 is the ordinary answer for a visitor, not a failure worth showing anyone.
      if (!(error instanceof ApiError) || error.status !== 401) console.error(error)
      setMe(null)
    } finally {
      setLoading(false)
    }
  }, [])

  /**
   * Inside Telegram there is nobody to ask for an email.
   *
   * The client hands the page a signed statement of who is looking at it, so a launch is
   * already an authenticated one — this trades it for a session before the first screen
   * decides whether to show a sign-in prompt. Tried once, after the ordinary check: if a
   * cookie is already good, nothing here needs to happen.
   */
  const enterFromTelegram = useCallback(async () => {
    const app = webApp()
    if (app === null) return null
    try {
      return await api.enterFromTelegram(app.initData)
    } catch (error) {
      console.error(error)
      return null
    }
  }, [])

  useEffect(() => {
    settle()
    void (async () => {
      try {
        setMe(await api.me())
      } catch {
        setMe(insideTelegram() ? await enterFromTelegram() : null)
      } finally {
        setLoading(false)
      }
    })()
  }, [enterFromTelegram])

  const value = useMemo(() => ({ me, loading, refresh }), [me, loading, refresh])
  return <SessionContext value={value}>{children}</SessionContext>
}
