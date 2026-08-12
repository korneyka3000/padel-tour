/**
 * Who somebody plays with, and who they play against.
 *
 * The table knows a player won five matches. It has never known who was on the other end of
 * them, which is the question a group actually argues about — who carries whom, and who you
 * can never beat.
 *
 * Most-played first, and the count is always next to the rate. One match won together is
 * 100%, and a screen showing only the percentage would be lying with a true number.
 */

import { Link } from 'react-router'

import type { Together } from '../lib/api'
import { useT } from './Locale'

/** Below this, a win rate is noise. Shown, but not called anybody's best or worst. */
const ENOUGH = 3

export function Company({ partners, opponents }: { partners: Together[]; opponents: Together[] }) {
  const t = useT()

  if (partners.length === 0) return null

  return (
    <section className="section" aria-labelledby="company-heading">
      <div className="section-head">
        <h2 id="company-heading">{t('company.title')}</h2>
      </div>

      <div className="company">
        <Column title={t('company.partners')} lines={partners} best="high" />
        <Column title={t('company.opponents')} lines={opponents} best="low" />
      </div>
    </section>
  )
}

/**
 * One side of the net.
 *
 * `best` says which end of the win rate is the interesting one: alongside a good partner you
 * win, against a hard opponent you do not, and the same number means opposite things.
 */
function Column({
  title,
  lines,
  best,
}: {
  title: string
  lines: Together[]
  best: 'high' | 'low'
}) {
  const t = useT()
  const eligible = lines.filter((line) => line.played >= ENOUGH)
  const standout = eligible.reduce<Together | null>((found, line) => {
    if (found === null) return line
    return best === 'high'
      ? line.win_rate > found.win_rate
        ? line
        : found
      : line.win_rate < found.win_rate
        ? line
        : found
  }, null)

  return (
    <div className="company-column">
      <h3 className="company-heading">{title}</h3>
      <ul className="company-list">
        {lines.map((line) => (
          <li className="company-row" key={line.player_id}>
            <Link className="company-name" to={`/p/${line.player_id}`}>
              {line.name}
            </Link>
            <span className="company-count">{t.count('matches', line.played)}</span>
            <span
              className={`company-rate${line.player_id === standout?.player_id ? ' is-standout' : ''}`}
            >
              {Math.round(line.win_rate * 100)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}
