/**
 * The admin section: five views behind one route, and the reason it exists at all.
 *
 * For a while an administrator was a capability rather than a place — somebody the
 * permission checks did not stop, using the ordinary screens. That still holds and is still
 * the better half of the design: the person fixing a group's tournament at eleven at night
 * wants the screens that group uses.
 *
 * What it could not do was answer questions no ordinary screen asks. Nobody could see who
 * had an account, or how they signed in, or what the whole thing added up to; a group could
 * be created but never removed. Those are the five views here, and nothing else.
 *
 * They live inside this app rather than in a second one, which answers the old objection to
 * an admin panel: the same sign-in, the same refusals, the same words, and a table browser
 * that by construction contains whatever broke.
 */

import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { TournamentList } from '../components/Archive'
import { Failed, Loading, useAsync } from '../components/Async'
import { useT } from '../components/Locale'
import type { AccountRow, Doomed, Group, Merge, TablePage } from '../lib/api'
import { api } from '../lib/api'
import { useSession } from '../lib/auth'

const SECTIONS = ['people', 'groups', 'tournaments', 'data'] as const
type Section = (typeof SECTIONS)[number]

export function AdminPage() {
  const t = useT()
  const { me, loading } = useSession()
  const { section } = useParams()

  if (loading) return <Loading />

  // Not a security boundary — every endpoint refuses on its own. This is so that somebody
  // who lands on the URL is told, rather than shown five panels of red.
  if (!me?.is_admin) {
    return (
      <>
        <header>
          <h1 className="title">{t('admin.title')}</h1>
          <p className="subtitle">{t('admin.notYou')}</p>
        </header>
        <Link className="back" to="/">
          {t('nav.home')}
        </Link>
      </>
    )
  }

  const current: Section | null = SECTIONS.includes(section as Section)
    ? (section as Section)
    : null

  return (
    <>
      <Link className="back" to="/">
        {t('nav.home')}
      </Link>

      <header>
        <p className="eyebrow">{t('admin.eyebrow')}</p>
        <h1 className="title">{t('admin.title')}</h1>
      </header>

      <nav className="admin-tabs">
        <Link className={`admin-tab${current === null ? ' is-on' : ''}`} to="/admin">
          {t('admin.overview')}
        </Link>
        {SECTIONS.map((name) => (
          <Link
            className={`admin-tab${current === name ? ' is-on' : ''}`}
            key={name}
            to={`/admin/${name}`}
          >
            {t(`admin.${name}`)}
          </Link>
        ))}
      </nav>

      {current === null && <Overview />}
      {current === 'people' && <People />}
      {current === 'groups' && <Groups />}
      {current === 'tournaments' && <Tournaments />}
      {current === 'data' && <Data />}
    </>
  )
}

/** How big the whole thing is, and whether the schema matches the code. */
function Overview() {
  const t = useT()
  const { data, error, loading } = useAsync(
    async () => ({
      totals: await api.admin.totals(),
      health: await api.health(),
    }),
    [],
  )

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />
  if (!data) return null

  const figures = [
    ['admin.accounts', data.totals.accounts],
    ['admin.groupsCount', data.totals.groups],
    ['admin.playersCount', data.totals.players],
    ['admin.tournamentsCount', data.totals.tournaments],
  ] as const

  return (
    <>
      <section className="section" aria-label={t('admin.overview')}>
        <dl className="figures">
          {figures.map(([label, value]) => (
            <div className="figure" key={label}>
              <dt>{t(label)}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="section" aria-labelledby="health-heading">
        <div className="section-head">
          <h2 id="health-heading">{t('admin.health')}</h2>
        </div>
        {/* The same answer the deploy pipeline waits for: it compares the mapped schema
            against the database and names any column the code believes in and the database
            has not got. */}
        <p className={data.health.status === 'ok' ? 'subtitle' : 'field-error'}>
          {data.health.status} · {data.health.database}
        </p>
      </section>
    </>
  )
}

function People() {
  const t = useT()
  const [reload, setReload] = useState(0)
  const { data, error, loading } = useAsync(() => api.admin.accounts(), [reload])

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />

  return (
    <section className="section" aria-labelledby="people-heading">
      <div className="section-head">
        <h2 id="people-heading">{t('admin.people')}</h2>
        <span className="eyebrow">{data?.length ?? 0}</span>
      </div>
      <div className="admin-rows">
        {(data ?? []).map((row) => (
          <Person
            account={row}
            others={(data ?? []).filter((one) => one.id !== row.id)}
            key={row.id}
            onChanged={() => setReload(reload + 1)}
          />
        ))}
      </div>
    </section>
  )
}

/**
 * One account.
 *
 * The display name is usually absent — an account only has one if some integration happened
 * to supply it — so the identity is the line that actually says who this is.
 */
function Person({
  account,
  others,
  onChanged,
}: {
  account: AccountRow
  others: AccountRow[]
  onChanged: () => void
}) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function detach(name: string, playerId: string) {
    if (!window.confirm(t('admin.confirmDetach', { name }))) return
    setBusy(true)
    setError(null)
    try {
      await api.admin.detach(playerId)
      onChanged()
    } catch (failure) {
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="admin-row">
      <div className="admin-row-main">
        <span className="admin-row-title">
          {account.display_name ?? t('admin.noName')}
          {account.is_admin && <span className="admin-badge">{t('admin.badge')}</span>}
        </span>
        <span className="card-meta">
          {account.identities.map((one) => `${one.provider}: ${one.external_id}`).join(' · ') ||
            t('admin.noWayIn')}
        </span>
        <span className="card-meta">
          {t('admin.lastSeen')}:{' '}
          {account.last_seen ? t.date(account.last_seen) : t('admin.never')}
        </span>
      </div>
      <div className="admin-row-side">
        {account.players.length === 0 ? (
          <span className="card-meta">{t('admin.noPlayers')}</span>
        ) : (
          account.players.map((player) => (
            <span className="admin-chip" key={player.id}>
              {player.name}
              <button
                className="link-button is-danger"
                type="button"
                disabled={busy}
                onClick={() => void detach(player.name, player.id)}
              >
                {t('admin.detach')}
              </button>
            </span>
          ))
        )}
        {others.length > 0 && <MergeInto account={account} others={others} onChanged={onChanged} />}
        {busy && <span className="card-meta">…</span>}
        {error && <span className="field-error">{error}</span>}
      </div>
    </div>
  )
}

/**
 * Joining one account to another.
 *
 * One person, two accounts, because the two doors mint different ones — a magic link
 * resolves by address, a bot link by account. Somebody who used both appears twice with
 * their history split down the middle, and nothing else in the app can put it back.
 *
 * This account is the one that disappears. Picking the survivor from a list rather than
 * typing an id, and showing what moves before it moves, because the operation is not
 * reversible and the numbers are the only thing that makes the question answerable.
 */
function MergeInto({
  account,
  others,
  onChanged,
}: {
  account: AccountRow
  others: AccountRow[]
  onChanged: () => void
}) {
  const t = useT()
  const [into, setInto] = useState('')
  const [preview, setPreview] = useState<Merge | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function look(target: string) {
    setInto(target)
    setPreview(null)
    setError(null)
    if (!target) return
    try {
      setPreview(await api.admin.mergePreview(account.id, target))
    } catch (failure) {
      setError(t.say(failure))
    }
  }

  async function join() {
    if (!preview?.possible) return
    const rows = Object.entries(preview.moving)
      .map(([table, count]) => `${table}: ${count}`)
      .join(', ')
    if (!window.confirm(t('admin.confirmMerge', { rows: rows || t('admin.nothingToMove') }))) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.admin.merge(account.id, into)
      onChanged()
    } catch (failure) {
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="admin-merge">
      <select
        className="field-input"
        aria-label={t('admin.mergeInto')}
        value={into}
        onChange={(event) => void look(event.target.value)}
      >
        <option value="">{t('admin.mergeInto')}</option>
        {others.map((one) => (
          <option value={one.id} key={one.id}>
            {one.identities.map((way) => way.external_id).join(', ') || one.id}
          </option>
        ))}
      </select>
      {preview && !preview.possible && (
        <span className="field-error">{preview.conflicts.join('; ')}</span>
      )}
      {preview?.possible && (
        <button
          className="link-button is-danger"
          type="button"
          disabled={busy}
          onClick={() => void join()}
        >
          {busy ? '…' : t('admin.merge')}
        </button>
      )}
      {error && <span className="field-error">{error}</span>}
    </span>
  )
}

function Groups() {
  const t = useT()
  const [reload, setReload] = useState(0)
  const { data, error, loading } = useAsync(() => api.admin.groups(), [reload])

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />

  return (
    <section className="section" aria-labelledby="groups-heading">
      <div className="section-head">
        <h2 id="groups-heading">{t('admin.groups')}</h2>
        <span className="eyebrow">{data?.length ?? 0}</span>
      </div>
      <div className="admin-rows">
        {(data ?? []).map((group) => (
          <GroupRow group={group} key={group.id} onChanged={() => setReload(reload + 1)} />
        ))}
      </div>
    </section>
  )
}

/**
 * One group, and the only genuinely destructive control in here.
 *
 * The foreign keys cascade, so deleting a group takes its roster and every tournament it
 * ever played. The confirmation asks the server what that is first and puts the numbers in
 * the question — a yes to "are you sure?" is not a yes to losing eleven tournaments.
 */
function GroupRow({ group, onChanged }: { group: Group; onChanged: () => void }) {
  const t = useT()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [gone, setGone] = useState<Doomed | null>(null)

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      const doomed = await api.admin.impact(group.id)
      const asked = t('admin.confirmDelete', {
        name: doomed.name,
        players: doomed.players,
        tournaments: doomed.tournaments,
      })
      if (!window.confirm(asked)) return
      setGone(await api.admin.deleteGroup(group.id))
      onChanged()
    } catch (failure) {
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  if (gone) {
    return (
      <div className="admin-row">
        <span className="card-meta">
          {t('admin.deleted', {
            name: gone.name,
            players: gone.players,
            tournaments: gone.tournaments,
          })}
        </span>
      </div>
    )
  }

  return (
    <div className="admin-row">
      <div className="admin-row-main">
        <Link className="admin-row-title" to={`/g/${group.id}`}>
          {group.name}
        </Link>
        <span className="card-meta">{t.count('players', group.player_count)}</span>
      </div>
      <div className="admin-row-side">
        <button
          className="link-button is-danger"
          type="button"
          disabled={busy}
          onClick={() => void remove()}
        >
          {busy ? '…' : t('admin.delete')}
        </button>
        {error && <span className="field-error">{error}</span>}
      </div>
    </div>
  )
}

function Tournaments() {
  const t = useT()
  const { data, error, loading } = useAsync(() => api.admin.tournaments(), [])

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />

  return (
    <section className="section" aria-labelledby="tournaments-heading">
      <div className="section-head">
        <h2 id="tournaments-heading">{t('admin.tournaments')}</h2>
        <span className="eyebrow">{data?.length ?? 0}</span>
      </div>
      <TournamentList entries={data ?? []} />
    </section>
  )
}

/**
 * The table browser.
 *
 * Read-only and general, which is the point: an admin panel containing only what somebody
 * anticipated is the one that will not contain whatever broke. Columns holding hashes are
 * withheld, and the screen says so rather than leaving their absence a mystery.
 */
function Data() {
  const t = useT()
  const [chosen, setChosen] = useState<string | null>(null)
  const tables = useAsync(() => api.admin.tables(), [])
  const page = useAsync(
    async () => (chosen === null ? null : await api.admin.table(chosen)),
    [chosen],
  )

  if (tables.loading) return <Loading />
  if (tables.error) return <Failed failure={tables.error} />

  return (
    <section className="section" aria-labelledby="data-heading">
      <div className="section-head">
        <h2 id="data-heading">{t('admin.data')}</h2>
      </div>

      <div className="admin-tables">
        {(tables.data ?? []).map((table) => (
          <button
            className={`admin-chip is-button${chosen === table.name ? ' is-on' : ''}`}
            key={table.name}
            type="button"
            onClick={() => setChosen(table.name)}
          >
            {table.name} <span className="card-meta">{table.rows}</span>
          </button>
        ))}
      </div>

      {page.error ? <Failed failure={page.error} /> : null}
      {page.data && <Rows page={page.data} />}
    </section>
  )
}

function Rows({ page }: { page: TablePage }) {
  const t = useT()

  return (
    <>
      {page.redacted.length > 0 && (
        <p className="aside">{t('admin.withheld', { columns: page.redacted.join(', ') })}</p>
      )}
      {/* Its own scroller: twelve columns of UUIDs are wider than any phone, and a page
          that scrolls sideways as a whole is a page nobody can read. */}
      <div className="admin-scroll">
        <table className="table admin-table">
          <thead>
            <tr>
              {page.columns.map((column) => (
                <th scope="col" key={column}>
                  {column}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {page.rows.map((row, index) => (
              <tr key={page.columns.map((column) => row[column]).join('|') || index}>
                {page.columns.map((column) => (
                  <td key={column}>{row[column] ?? '—'}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="card-meta">
        {t('admin.showing', { shown: page.rows.length, total: page.total })}
      </p>
    </>
  )
}
