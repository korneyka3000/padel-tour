/** One tournament: where play has got to, the table, and the climb. */

import { Link, useParams } from 'react-router'

import { Climb } from '../components/Climb'
import { Failed, Loading } from '../components/Async'
import { useAsync } from '../components/Async'
import { CourtGrid } from '../components/Court'
import { Standings } from '../components/Standings'
import { FORMAT_LABEL, api, formatDate, plural } from '../lib/api'

export function TournamentPage() {
  const { id = '' } = useParams()
  const { data, error, loading } = useAsync(() => api.tournament(id), [id])

  if (loading) return <Loading />
  if (error) return <Failed message={error} />
  if (!data) return null

  const showing = data.rounds.find((round) => !round.complete) ?? data.rounds.at(-1)
  const players = data.standings.length

  return (
    <>
      <Link className="back" to={`/g/${data.group_id}`}>
        ← К группе
      </Link>

      <header>
        <p className="eyebrow">
          {data.finished ? 'Завершён' : 'Идёт сейчас'} · {formatDate(data.created_at)}
        </p>
        <h1 className="title">{FORMAT_LABEL[data.format]}</h1>
        <p className="subtitle">
          {players} {plural(players, 'игрок', 'игрока', 'игроков')} · матч до{' '}
          {data.points_per_match} · {data.total_rounds}{' '}
          {plural(data.total_rounds, 'раунд', 'раунда', 'раундов')}
        </p>
      </header>

      {showing && <CourtGrid round={showing} totalRounds={data.total_rounds} />}

      <Standings rows={data.standings} />

      <Climb progression={data.progression} />
    </>
  )
}
