/** The table. Points decide it; the difference is there because it reads well. */

import { Link } from 'react-router'

import type { Standing } from '../lib/api'

const PODIUM = 3

export function Standings({ rows }: { rows: Standing[] }) {
  return (
    <section className="section" aria-labelledby="standings-heading">
      <div className="section-head">
        <h2 id="standings-heading">Таблица</h2>
      </div>
      <table className="table">
        <thead>
          <tr>
            {/* The column stays in the layout; only its label is for screen readers. */}
            <th scope="col">
              <span className="visually-hidden">Место</span>
            </th>
            <th scope="col">Игрок</th>
            <th scope="col">Матчи</th>
            <th scope="col">Победы</th>
            <th scope="col">Очки</th>
            <th scope="col">Разница</th>
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
