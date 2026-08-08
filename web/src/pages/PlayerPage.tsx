/** One player's record. */

import { Link, useParams } from 'react-router'

import { Failed, Loading, Note, useAsync } from '../components/Async'
import { FORMAT_LABEL, api, formatDate, plural } from '../lib/api'

export function PlayerPage() {
  const { id = '' } = useParams()
  const { data, error, loading } = useAsync(() => api.player(id), [id])

  if (loading) return <Loading />
  if (error) return <Failed message={error} />
  if (!data) return null

  const figures: Array<[string, string]> = [
    ['Турниров', String(data.tournaments)],
    ['Матчей', String(data.matches)],
    ['Побед', String(data.wins)],
    ['Очков за матч', data.matches ? data.average_points.toFixed(1) : '—'],
    ['Лучшее место', data.best_rank ? String(data.best_rank) : '—'],
    ['Призовых', String(data.podiums)],
  ]

  return (
    <>
      <header>
        <p className="eyebrow">Игрок</p>
        <h1 className="title">{data.name}</h1>
      </header>

      <section className="section" aria-label="Сводка">
        <dl className="figures">
          {figures.map(([label, value]) => (
            <div className="figure" key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="section" aria-labelledby="history-heading">
        <div className="section-head">
          <h2 id="history-heading">Турниры</h2>
          <span className="eyebrow">{data.history.length}</span>
        </div>

        {data.history.length === 0 ? (
          <Note title="Ещё не играл">Сыграйте турнир — он появится здесь.</Note>
        ) : (
          <div className="cards">
            {data.history.map((entry) => (
              <Link className="card" key={entry.id} to={`/t/${entry.id}`}>
                <span>
                  <span className="card-title">{FORMAT_LABEL[entry.format]}</span>
                  <span className="card-meta">
                    {formatDate(entry.created_at)} · {entry.player_count}{' '}
                    {plural(entry.player_count, 'игрок', 'игрока', 'игроков')}
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
    </>
  )
}
