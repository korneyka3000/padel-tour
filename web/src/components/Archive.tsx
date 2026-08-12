/**
 * One tournament as a line in a list, wherever that list is.
 *
 * Two places show it now — a group's archive, and your own history across groups — and the
 * difference between them is not worth a second component. It is worth two optional fields:
 * the group's name, which only matters when the list spans more than one, and where you
 * finished, which only exists when the list is about you.
 *
 * The server decides. It fills those in for "my tournaments" and leaves them out of a
 * group's archive, where the group is already the page you are on.
 */

import { Link } from 'react-router'

import type { TournamentCard } from '../lib/api'
import { useT } from './Locale'

export function TournamentLine({ entry }: { entry: TournamentCard }) {
  const t = useT()

  const meta = [
    t.date(entry.created_at),
    entry.group_name,
    t.count('players', entry.player_count),
    entry.finished
      ? null
      : t('group.playedOf', { played: entry.rounds_played, total: entry.total_rounds }),
  ].filter(Boolean)

  return (
    <Link className="card" to={`/t/${entry.id}`}>
      <span>
        <span className="card-title">{t(`format.${entry.format}`)}</span>
        <span className="card-meta">{meta.join(' · ')}</span>
      </span>
      {/* Where you came, when the list is about you; otherwise who won it. Never both —
          on your own history, "winner: Корней" where Корней is you reads as a stranger. */}
      {entry.my_rank !== null ? (
        <span className="card-winner">
          {t('archive.yourPlace')}
          <b className={entry.my_rank <= 3 ? 'is-podium' : undefined}>{entry.my_rank}</b>
        </span>
      ) : (
        entry.winner_name && (
          <span className="card-winner">
            {t('group.winner')}
            <b>{entry.winner_name}</b>
          </span>
        )
      )}
    </Link>
  )
}

export function TournamentList({ entries }: { entries: TournamentCard[] }) {
  return (
    <div className="cards">
      {entries.map((entry) => (
        <TournamentLine entry={entry} key={entry.id} />
      ))}
    </div>
  )
}
