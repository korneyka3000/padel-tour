/** Asks the server who is signed in, once, and tells the rest of the app. */

import { useCallback, useEffect, useMemo, useState } from 'react'

import { ApiError, api, type Me } from '../lib/api'
import { SessionContext } from '../lib/auth'

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

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo(() => ({ me, loading, refresh }), [me, loading, refresh])
  return <SessionContext value={value}>{children}</SessionContext>
}
