/**
 * How a finished tournament opens.
 *
 * A tournament that is over is a different page from one in progress, and it was not being
 * treated as one: the courts came first, the table third, and the result — the thing anybody
 * opening it afterwards came for — was a row in a table below the fold.
 *
 * Three places, silver and bronze flanking a taller gold, in the order they are read on a
 * real podium rather than 1-2-3 left to right. The bot has had this since the finish screen
 * was reworked; the web had nothing.
 */

import { Link } from 'react-router'

import type { Standing } from '../lib/api'
import { useT } from './Locale'

/** Second, first, third — the order they stand in, not the order they finished. */
const ORDER = [2, 1, 3]

export function Podium({ rows }: { rows: Standing[] }) {
  const t = useT()

  const places = ORDER.map((rank) => rows.find((row) => row.rank === rank)).filter(
    (row): row is Standing => row !== undefined,
  )

  // Fewer than three finishers is possible — a tournament abandoned early, or a tie that
  // leaves no third. A podium with one step on it is worse than the table underneath.
  if (places.length < ORDER.length) return null

  return (
    <section className="section" aria-labelledby="podium-heading">
      <div className="section-head">
        <h2 id="podium-heading">{t('podium.title')}</h2>
      </div>
      <ol className="podium">
        {places.map((row) => (
          <li className={`step step-${row.rank}`} key={row.player_id}>
            <span className="step-rank" aria-hidden="true">
              {row.rank}
            </span>
            <Link className="step-name" to={`/p/${row.player_id}`}>
              {row.name}
            </Link>
            <span className="step-points">
              {t('podium.points', { points: row.points_for })}
            </span>
            <span className="step-block" aria-hidden="true" />
          </li>
        ))}
      </ol>
    </section>
  )
}
