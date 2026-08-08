/** The way in when nobody handed you a link. */

import { useState } from 'react'
import { Link } from 'react-router'

import { Loading } from '../components/Async'
import { api } from '../lib/api'
import { plural } from '../lib/api'
import { useSession } from '../lib/auth'

export function HomePage() {
  const { me, loading, refresh } = useSession()

  return (
    <>
      <header>
        <p className="eyebrow">Американо · Мексикано</p>
        <h1 className="title">Padel Tour</h1>
        <p className="subtitle">Кто с кем играет, кто впереди и как это менялось.</p>
      </header>

      {loading ? <Loading /> : me ? <Groups groups={me.groups} onChange={refresh} /> : <Invitation />}
    </>
  )
}

/** What a visitor sees. Nothing is listed, because groups belong to the people in them. */
function Invitation() {
  return (
    <section className="section">
      <div className="section-head">
        <h2>Начните здесь</h2>
      </div>
      <p className="subtitle">
        Группы видны только своим. Войдите по ссылке из почты — или откройте приглашение,
        если вам его прислали.
      </p>
      <Link className="button" to="/sign-in">
        Войти
      </Link>
      <p className="aside">
        В Telegram проще: добавьте бота в чат и напишите <code>/start</code>.
      </p>
    </section>
  )
}

function Groups({
  groups,
  onChange,
}: {
  groups: { id: string; name: string; player_count: number }[]
  onChange: () => Promise<void>
}) {
  return (
    <section className="section" aria-labelledby="groups-heading">
      <div className="section-head">
        <h2 id="groups-heading">Ваши группы</h2>
      </div>

      {groups.length === 0 ? (
        <p className="subtitle">Пока ни одной. Заведите свою — вы станете её владельцем.</p>
      ) : (
        <div className="cards">
          {groups.map((group) => (
            <Link className="card" key={group.id} to={`/g/${group.id}`}>
              <span className="card-title">{group.name}</span>
              <span className="card-meta">
                {group.player_count} {plural(group.player_count, 'игрок', 'игрока', 'игроков')}
              </span>
            </Link>
          ))}
        </div>
      )}

      <NewGroup onCreated={onChange} />
    </section>
  )
}

function NewGroup({ onCreated }: { onCreated: () => Promise<void> }) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.createGroup(name.trim())
      setName('')
      await onCreated()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не создалась')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form form-inline" onSubmit={submit}>
      <label className="field">
        <span className="field-label">Новая группа</span>
        <input
          className="field-input"
          type="text"
          required
          maxLength={80}
          placeholder="Вторничный падел"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <button className="button" type="submit" disabled={busy || name.trim().length === 0}>
        {busy ? 'Заводим…' : 'Завести'}
      </button>
      {error && <p className="field-error">{error}</p>}
    </form>
  )
}
