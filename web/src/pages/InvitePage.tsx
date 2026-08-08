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
import { api } from '../lib/api'
import { rememberDestination, useSession } from '../lib/auth'

export function InvitePage() {
  const { token = '' } = useParams()
  const navigate = useNavigate()
  const { me, loading: checking, refresh } = useSession()
  const { data: player, error, loading } = useAsync(() => api.invitation(token), [token])
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  if (loading || checking) return <Loading />
  if (error) return <Failed message={error} />
  if (!player) return <Note title="Приглашение не найдено" />

  async function accept() {
    setBusy(true)
    setFailure(null)
    try {
      await api.acceptInvitation(token)
      await refresh()
      void navigate('/', { replace: true })
    } catch (problem) {
      setFailure(problem instanceof Error ? problem.message : 'Не получилось')
      setBusy(false)
    }
  }

  return (
    <>
      <header>
        <p className="eyebrow">Приглашение</p>
        <h1 className="title">Вы — {player.name}</h1>
        <p className="subtitle">
          Приняв, вы получите свою историю матчей и сможете вносить счёт в своих играх.
        </p>
      </header>

      {me ? (
        <div className="form">
          <button className="button" type="button" onClick={() => void accept()} disabled={busy}>
            {busy ? 'Принимаем…' : `Играть как ${player.name}`}
          </button>
          {failure && <p className="field-error">{failure}</p>}
        </div>
      ) : (
        <div className="form">
          <p className="subtitle">Чтобы приглашение осталось за вами, сначала войдите.</p>
          <Link
            className="button"
            to="/sign-in"
            onClick={() => rememberDestination(`/i/${token}`)}
          >
            Войти и продолжить
          </Link>
        </div>
      )}
    </>
  )
}
