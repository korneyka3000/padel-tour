/** A group: what is being played right now, then everything that came before. */

import { Link, useParams } from 'react-router'

import { Failed, Loading, Note, useAsync } from '../components/Async'
import { Climb } from '../components/Climb'
import { CourtGrid } from '../components/Court'
import { Standings } from '../components/Standings'
import type { GroupDetail, Tournament, TournamentCard } from '../lib/api'
import { FORMAT_LABEL, api, formatDate, plural } from '../lib/api'

interface Loaded {
  group: GroupDetail
  active: Tournament | null
  archive: TournamentCard[]
}

export function GroupPage() {
  const { id = '' } = useParams()
  const { data, error, loading } = useAsync<Loaded>(
    async () => {
      const [group, active, archive] = await Promise.all([
        api.group(id),
        api.active(id),
        api.archive(id),
      ])
      return { group, active, archive }
    },
    [id],
  )

  if (loading) return <Loading />
  if (error) return <Failed message={error} />
  if (!data) return null

  const { group, active, archive } = data
  const past = archive.filter((entry) => entry.id !== active?.id)
  const showing = active?.rounds.find((round) => !round.complete) ?? active?.rounds.at(-1)

  return (
    <>
      <header>
        <p className="eyebrow">
          {group.players.length}{' '}
          {plural(group.players.length, 'игрок', 'игрока', 'игроков')}
        </p>
        <h1 className="title">{group.name}</h1>
        {active ? (
          <p className="subtitle">
            Сейчас идёт {FORMAT_LABEL[active.format].toLowerCase()} — раунд{' '}
            {active.rounds_played + 1} из {active.total_rounds}
          </p>
        ) : (
          <p className="subtitle">Сейчас никто не играет</p>
        )}
      </header>

      {active && showing && (
        <>
          <CourtGrid round={showing} totalRounds={active.total_rounds} />
          <Standings rows={active.standings} />
          <Climb progression={active.progression} />
        </>
      )}

      <section className="section" aria-labelledby="archive-heading">
        <div className="section-head">
          <h2 id="archive-heading">Прошедшие турниры</h2>
          <span className="eyebrow">{past.length}</span>
        </div>

        {past.length === 0 ? (
          <Note title="Пока ни одного">
            Соберите турнир в телеграме — он появится здесь.
          </Note>
        ) : (
          <div className="cards">
            {past.map((entry) => (
              <Link className="card" key={entry.id} to={`/t/${entry.id}`}>
                <span>
                  <span className="card-title">{FORMAT_LABEL[entry.format]}</span>
                  <span className="card-meta">
                    {formatDate(entry.created_at)} · {entry.player_count}{' '}
                    {plural(entry.player_count, 'игрок', 'игрока', 'игроков')}
                    {entry.finished ? '' : ` · сыграно ${entry.rounds_played} из ${entry.total_rounds}`}
                  </span>
                </span>
                {entry.winner_name && (
                  <span className="card-winner">
                    победитель
                    <b>{entry.winner_name}</b>
                  </span>
                )}
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="section" aria-labelledby="roster-heading">
        <div className="section-head">
          <h2 id="roster-heading">Состав</h2>
        </div>
        <ul className="roster">
          {group.players.map((player) => (
            <li key={player.id}>
              <Link className="roster-chip" to={`/p/${player.id}`}>
                {player.name}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </>
  )
}
