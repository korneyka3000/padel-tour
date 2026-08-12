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
import { useT } from './Locale'

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
  const t = useT()

  return (
    <section className="section" aria-labelledby="roster-heading">
      <div className="section-head">
        <h2 id="roster-heading">{t('roster.title')}</h2>
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
  const t = useT()
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
      setError(t.say(failure))
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
      setError(t.say(failure))
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
          aria-label={t('roster.newNameFor', { name: player.name })}
          onChange={(event) => setName(event.target.value)}
        />
        <button className="button button-small" type="submit" disabled={busy}>
          {busy ? '…' : t('roster.ok')}
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
          {t('roster.cancel')}
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
            {t('roster.rename')}
          </button>
          {player.is_claimed ? (
            /* Already somebody's. The server refuses a second invitation for the same
               player, so offering one is offering a refusal. */
            <span className="roster-claimed">{t('roster.claimed')}</span>
          ) : (
            <InviteLink playerId={player.id} name={player.name} />
          )}
          <button
            className="link-button"
            type="button"
            disabled={busy}
            onClick={() => void remove()}
          >
            {t('roster.remove')}
          </button>
        </span>
      )}
      {error && <span className="field-error">{error}</span>}
    </>
  )
}

/**
 * Turning a name on the roster into a person.
 *
 * A player is a name the owner typed. It carries the history — seven tournaments, a rank, a
 * points-per-match — and belongs to nobody, so none of that reaches the person it is about.
 * An invitation is how "Аня" the row becomes Аня the account: a single-use link, tied to
 * that one player, that the owner sends however they normally reach her.
 *
 * It used to appear as a bare input containing a URL, with nothing saying what the URL was
 * or what to do with it. The link is the same; everything around it is new.
 */
function InviteLink({ playerId, name }: { playerId: string; name: string }) {
  const t = useT()
  const [link, setLink] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function issue() {
    setError(null)
    try {
      const invitation = await api.invite(playerId)
      setLink(`${window.location.origin}/i/${invitation.token}`)
    } catch (failure) {
      setError(t.say(failure))
    }
  }

  async function copy() {
    if (link === null) return
    try {
      await navigator.clipboard.writeText(link)
      setCopied(true)
    } catch {
      // Clipboard access can be refused, and on a page where the link is already visible
      // and selectable that is not worth an error message.
      setCopied(false)
    }
  }

  if (error) return <span className="field-error">{error}</span>

  if (link !== null) {
    return (
      <span className="invite">
        <span className="invite-what">{t('roster.inviteExplain', { name })}</span>
        <span className="invite-row">
          <input
            className="field-input field-copy"
            readOnly
            value={link}
            aria-label={t('roster.inviteLinkFor', { name })}
            onFocus={(event) => event.target.select()}
          />
          <button className="button button-small" type="button" onClick={() => void copy()}>
            {copied ? t('roster.copied') : t('roster.copy')}
          </button>
        </span>
        <span className="invite-terms">{t('roster.inviteTerms')}</span>
      </span>
    )
  }

  return (
    <button className="link-button" type="button" onClick={() => void issue()}>
      {t('roster.invite')}
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
  const t = useT()
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
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="form form-inline" onSubmit={submit}>
      <label className="field">
        <span className="field-label">{t('roster.addPlayer')}</span>
        <input
          className="field-input"
          type="text"
          required
          maxLength={80}
          placeholder={t('roster.addPlaceholder')}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <button className="button" type="submit" disabled={busy || name.trim().length === 0}>
        {busy ? t('roster.adding') : t('roster.add')}
      </button>
      {error && <p className="field-error">{error}</p>}
    </form>
  )
}
