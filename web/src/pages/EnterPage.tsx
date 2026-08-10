/**
 * Where a sign-in link lands.
 *
 * Nothing to decide here: exchange the token for a session and carry on to wherever the
 * person was headed before the email interrupted them.
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router'

import { Loading, Note } from '../components/Async'
import { useT } from '../components/Locale'
import { api } from '../lib/api'
import { takeDestination, useSession } from '../lib/auth'

export function EnterPage() {
  const t = useT()
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const { refresh } = useSession()
  const [error, setError] = useState<string | null>(null)
  // React runs effects twice in development. Redeeming twice would burn the token and
  // report a working link as broken.
  const started = useRef(false)

  const token = params.get('token') ?? ''

  useEffect(() => {
    if (started.current) return
    started.current = true

    if (!token) {
      setError(t('enter.noToken'))
      return
    }

    api
      .enter(token)
      .then(async () => {
        await refresh()
        void navigate(takeDestination(), { replace: true })
      })
      .catch((failure: unknown) => {
        setError(t.say(failure))
      })
  }, [token, refresh, navigate])

  if (error) {
    return (
      <Note title={t('enter.title')}>
        {error}. <Link to="/sign-in">{t('enter.askNew')}</Link>.
      </Note>
    )
  }
  return <Loading />
}
