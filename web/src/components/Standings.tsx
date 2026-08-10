/** The table. Points decide it; the difference is there because it reads well. */

import { Link } from 'react-router'

import type { Standing } from '../lib/api'
import { useT } from './Locale'

const PODIUM = 3

export function Standings({ rows }: { rows: Standing[] }) {
  const t = useT()

  return (
    <section className="section" aria-labelledby="standings-heading">
      <div className="section-head">
        <h2 id="standings-heading">{t('standings.title')}</h2>
      </div>
      <table className="table">
        <thead>
          <tr>
            {/* The column stays in the layout; only its label is for screen readers. */}
            <th scope="col">
              <span className="visually-hidden">{t('standings.place')}</span>
            </th>
            <th scope="col">{t('standings.player')}</th>
            <th scope="col">{t('standings.matches')}</th>
            <th scope="col">{t('standings.wins')}</th>
            <th scope="col">{t('standings.points')}</th>
            <th scope="col">{t('standings.diff')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.player_id}>
              <td className={`rank${row.rank <= PODIUM ? ' is-podium' : ''}`}>{row.rank}</td>
              <td className="name">
                <Link to={`/p/${row.player_id}`}>{row.name}</Link>
              </td>
              <td>{row.played}</td>
              <td>{row.wins}</td>
              <td className="points">{row.points_for}</td>
              <td className="diff">
                {row.diff > 0 ? '+' : ''}
                {row.diff}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}
