/**
 * The roster, plus the two things an owner does with it: add somebody, and invite them.
 *
 * An invitation is shown as a link to copy rather than emailed from here. The owner knows
 * how to reach these people — that is why they are on the roster — and guessing between
 * their email, their chat and their phone would be worse than handing over a link.
 */

import { useState } from 'react'
import { Link } from 'react-router'

import type { Player } from '../lib/api'
import { api } from '../lib/api'

export function Roster({
  groupId,
  players,
  canEdit,
  onChange,
}: {
  groupId: string
  players: Player[]
  canEdit: boolean
  onChange: (players: Player[]) => void
}) {
  return (
    <section className="section" aria-labelledby="roster-heading">
      <div className="section-head">
        <h2 id="roster-heading">Состав</h2>
        <span className="eyebrow">{players.length}</span>
      </div>

      <ul className={`roster${canEdit ? ' is-editable' : ''}`}>
        {players.map((player) => (
          <li key={player.id} className="roster-row">
            <Entry
              player={player}
              canEdit={canEdit}
              onRenamed={(renamed) =>
                onChange(players.map((one) => (one.id === renamed.id ? renamed : one)))
              }
              onRemoved={() => onChange(players.filter((one) => one.id !== player.id))}
            />
          </li>
        ))}
      </ul>

      {canEdit && <AddPlayer groupId={groupId} onAdded={onChange} />}
    </section>
  )
}

/**
 * One line of the roster: the name, and what an owner may do to it.
 *
 * Renaming happens in place rather than on a separate screen — it is almost always a typo
 * being fixed, and a typo does not deserve a page of its own.
 */
function Entry({
  player,
  canEdit,
  onRenamed,
  onRemoved,
}: {
  player: Player
  canEdit: boolean
  onRenamed: (player: Player) => void
  onRemoved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(player.name)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function save(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      onRenamed(await api.renamePlayer(player.id, name.trim()))
      setEditing(false)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не переименовался')
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    setBusy(true)
    setError(null)
    try {
      await api.removePlayer(player.id)
      onRemoved()
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не убрался')
      setBusy(false)
    }
  }

  if (editing) {
    return (
      <form className="roster-rename" onSubmit={save}>
        <input
          className="field-input"
          type="text"
          required
          maxLength={80}
          value={name}
          aria-label={`Новое имя для ${player.name}`}
          onChange={(event) => setName(event.target.value)}
        />
        <button className="button button-small" type="submit" disabled={busy}>
          {busy ? '…' : 'ОК'}
        </button>
        <button
          className="link-button"
          type="button"
          onClick={() => {
            setName(player.name)
            setEditing(false)
            setError(null)
          }}
        >
          отмена
        </button>
        {error && <span className="field-error">{error}</span>}
      </form>
    )
  }

  return (
    <>
      <Link className="roster-chip" to={`/p/${player.id}`}>
        {player.name}
      </Link>
      {canEdit && (
        <span className="roster-actions">
          <button className="link-button" type="button" onClick={() => setEditing(true)}>
            переименовать
          </button>
          <InviteLink playerId={player.id} name={player.name} />
          <button
            className="link-button"
            type="button"
            disabled={busy}
            onClick={() => void remove()}
          >
            убрать
          </button>
        </span>
      )}
      {error && <span className="field-error">{error}</span>}
    </>
  )
}

function InviteLink({ playerId, name }: { playerId: string; name: string }) {
  const [link, setLink] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function issue() {
    setError(null)
    try {
      const invitation = await api.invite(playerId)
      setLink(`${window.location.origin}/i/${invitation.token}`)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не выписалось')
    }
  }

  if (error) return <span className="field-error">{error}</span>

  if (link) {
    return (
      <input
        className="field-input field-copy"
        readOnly
        value={link}
        aria-label={`Ссылка-приглашение для ${name}`}
        onFocus={(event) => event.target.select()}
      />
    )
  }

  return (
    <button className="link-button" type="button" onClick={() => void issue()}>
      пригласить
    </button>
  )
}

function AddPlayer({
  groupId,
  onAdded,
}: {
  groupId: string
  onAdded: (players: Player[]) => void
}) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const group = await api.addPlayer(groupId, name.trim())
      setName('')
      onAdded(group.players)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не добавился')
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form form-inline" onSubmit={submit}>
      <label className="field">
        <span className="field-label">Добавить игрока</span>
        <input
          className="field-input"
          type="text"
          required
          maxLength={80}
          placeholder="Аня"
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <button className="button" type="submit" disabled={busy || name.trim().length === 0}>
        {busy ? 'Добавляем…' : 'Добавить'}
      </button>
      {error && <p className="field-error">{error}</p>}
    </form>
  )
}
