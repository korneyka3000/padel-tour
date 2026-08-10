/**
 * Accepting an invitation.
 *
 * The page names the player before asking for anything, because "join as Аня" is a very
 * different question from "sign in". Somebody who is already signed in accepts in one tap;
 * somebody who is not goes for a sign-in link and comes straight back here.
 */

import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { Failed, Loading, Note, useAsync } from '../components/Async'
import { useT } from '../components/Locale'
import { api } from '../lib/api'
import { rememberDestination, useSession } from '../lib/auth'

export function InvitePage() {
  const t = useT()
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const { me, loading: checking, refresh } = useSession()
  const { data: player, error, loading } = useAsync(() => api.invitation(token), [token])
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  if (loading || checking) return <Loading />
  if (error) return <Failed failure={error} />
  if (!player) return <Note title={t('invite.notFound')} />

  async function accept() {
    setBusy(true)
    setFailure(null)
    try {
      await api.acceptInvitation(token)
      await refresh()
      void navigate('/', { replace: true })
    } catch (problem) {
      setFailure(t.say(problem))
      setBusy(false)
    }
  }

  return (
    <>
      <header>
        <p className="eyebrow">{t('invite.eyebrow')}</p>
        <h1 className="title">{t('invite.youAre', { name: player.name })}</h1>
        <p className="subtitle">
          {t('invite.body')}
        </p>
      </header>

      {me ? (
        <div className="form">
          <button className="button" type="button" onClick={() => void accept()} disabled={busy}>
            {busy ? t('invite.accepting') : t('invite.accept', { name: player.name })}
          </button>
          {failure && <p className="field-error">{failure}</p>}
        </div>
      ) : (
        <div className="form">
          <p className="subtitle">{t('invite.signInFirst')}</p>
          <Link
            className="button"
            to="/sign-in"
            onClick={() => rememberDestination(`/i/${token}`)}
          >
            {t('invite.signInAndContinue')}
          </Link>
        </div>
      )}
    </>
  )
}
