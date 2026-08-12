/** One player's record. */

import { useParams } from 'react-router'

import { TournamentList } from '../components/Archive'
import { Failed, Loading, Note, useAsync } from '../components/Async'
import { Company } from '../components/Company'
import { useT } from '../components/Locale'
import { api } from '../lib/api'
import type { Key } from '../lib/i18n'

export function PlayerPage() {
  const t = useT()
  const { id = '' } = useParams()
  const { data, error, loading } = useAsync(() => api.player(id), [id])

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />
  if (!data) return null

  const figures: Array<[Key, string]> = [
    ['player.tournaments', String(data.tournaments)],
    ['player.matches', String(data.matches)],
    ['player.wins', String(data.wins)],
    ['player.pointsPerMatch', data.matches ? data.average_points.toFixed(1) : '—'],
    ['player.bestRank', data.best_rank ? String(data.best_rank) : '—'],
    ['player.podiums', String(data.podiums)],
  ]

  return (
    <>
      <header>
        <p className="eyebrow">{t('player.eyebrow')}</p>
        <h1 className="title">{data.name}</h1>
      </header>

      <section className="section" aria-label={t('player.summary')}>
        <dl className="figures">
          {figures.map(([label, value]) => (
            <div className="figure" key={label}>
              <dt>{t(label)}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      </section>

      <Company partners={data.partners} opponents={data.opponents} />

      <section className="section" aria-labelledby="history-heading">
        <div className="section-head">
          <h2 id="history-heading">{t('player.history')}</h2>
          <span className="eyebrow">{data.history.length}</span>
        </div>

        {data.history.length === 0 ? (
          <Note title={t('player.neverPlayed')}>{t('player.neverPlayedBody')}</Note>
        ) : (
          <TournamentList entries={data.history} />
        )}
      </section>
    </>
  )
}
