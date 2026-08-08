/** The way in when nobody handed you a link. */

import { Link } from 'react-router'

import { Failed, Loading, Note, useAsync } from '../components/Async'
import { api, plural } from '../lib/api'

export function HomePage() {
  const { data, error, loading } = useAsync(() => api.groups(), [])

  if (loading) return <Loading />
  if (error) return <Failed message={error} />

  return (
    <>
      <header>
        <p className="eyebrow">Американо · Мексикано</p>
        <h1 className="title">Padel Tour</h1>
        <p className="subtitle">Кто с кем играет, кто впереди и как это менялось.</p>
      </header>

      <section className="section" aria-labelledby="groups-heading">
        <div className="section-head">
          <h2 id="groups-heading">Группы</h2>
        </div>
        {!data || data.length === 0 ? (
          <Note title="Пока пусто">
            Добавьте бота в чат и напишите <code>/start</code> — группа появится здесь.
          </Note>
        ) : (
          <div className="cards">
            {data.map((group) => (
              <Link className="card" key={group.id} to={`/g/${group.id}`}>
                <span className="card-title">{group.name}</span>
                <span className="card-meta">
                  {group.player_count}{' '}
                  {plural(group.player_count, 'игрок', 'игрока', 'игроков')}
                </span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </>
  )
}
