/** The way in when nobody handed you a link. */

import { useState } from 'react'
import { Link } from 'react-router'

import { Loading } from '../components/Async'
import { api } from '../lib/api'
import { useT } from '../components/Locale'
import { useSession } from '../lib/auth'

export function HomePage() {
  const t = useT()
  const { me, loading, refresh } = useSession()

  return (
    <>
      <header>
        <p className="eyebrow">{t('home.formats')}</p>
        <h1 className="title">Padel Tour</h1>
        <p className="subtitle">{t('home.tagline')}</p>
      </header>

      {loading ? <Loading /> : me ? <Groups groups={me.groups} onChange={refresh} /> : <Invitation />}
    </>
  )
}

/** What a visitor sees. Nothing is listed, because groups belong to the people in them. */
function Invitation() {
  const t = useT()
  return (
    <section className="section">
      <div className="section-head">
        <h2>{t('home.startHere')}</h2>
      </div>
      <p className="subtitle">
        {t('home.startBody')}
      </p>
      <Link className="button" to="/sign-in">
        {t('nav.signIn')}
      </Link>
      <p className="aside">
        {t('home.telegramHint')} <code>/start</code>.
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
  const t = useT()

  return (
    <section className="section" aria-labelledby="groups-heading">
      <div className="section-head">
        <h2 id="groups-heading">{t('home.yourGroups')}</h2>
      </div>

      {groups.length === 0 ? (
        <p className="subtitle">{t('home.noGroups')}</p>
      ) : (
        <div className="cards">
          {groups.map((group) => (
            <Link className="card" key={group.id} to={`/g/${group.id}`}>
              <span className="card-title">{group.name}</span>
              <span className="card-meta">
                {t.count('players', group.player_count)}
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
  const t = useT()
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
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form form-inline" onSubmit={submit}>
      <label className="field">
        <span className="field-label">{t('home.newGroup')}</span>
        <input
          className="field-input"
          type="text"
          required
          maxLength={80}
          placeholder={t('home.newGroupPlaceholder')}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <button className="button" type="submit" disabled={busy || name.trim().length === 0}>
        {busy ? t('home.creating') : t('home.create')}
      </button>
      {error && <p className="field-error">{error}</p>}
    </form>
  )
}
