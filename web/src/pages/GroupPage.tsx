/** A group: what is being played right now, then everything that came before. */

import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { Failed, Loading, Note, useAsync } from '../components/Async'
import { Climb } from '../components/Climb'
import { CourtGrid } from '../components/Court'
import { TournamentList } from '../components/Archive'
import { Roster } from '../components/Roster'
import { Standings } from '../components/Standings'
import type { GroupDetail, Player, Tournament, TournamentCard } from '../lib/api'
import { useT } from '../components/Locale'
import { api } from '../lib/api'

interface Loaded {
  group: GroupDetail
  active: Tournament | null
  archive: TournamentCard[]
}

export function GroupPage() {
  const t = useT()
  const { id = '' } = useParams()
  // The roster changes under this page — a player added, an invitation issued — and
  // reloading the whole group to show one new name would throw away the tournament with it.
  const [roster, setRoster] = useState<Player[] | null>(null)
  const { data, error, loading } = useAsync<Loaded>(
    async () => {
      const [group, active, archive] = await Promise.all([
        api.group(id),
        api.active(id),
        api.archive(id),
      ])
      return { group, active, archive }
    },
    [id],
  )

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />
  if (!data) return null

  const { group, active, archive } = data
  const players = roster ?? group.players
  const past = archive.filter((entry) => entry.id !== active?.id)
  const showing = active?.rounds.find((round) => !round.complete) ?? active?.rounds.at(-1)

  return (
    <>
      <header>
        <p className="eyebrow">
          {t.count('players', players.length)}
        </p>
        <h1 className="title">{group.name}</h1>
        {active ? (
          <p className="subtitle">
            {t('group.nowPlaying', {
              format: t(`format.${active.format}`),
              round: active.rounds_played + 1,
              total: active.total_rounds,
            })}
          </p>
        ) : (
          <p className="subtitle">{t('group.nobodyPlaying')}</p>
        )}
        {group.is_owner && (
          <div className="actions">
            {active ? (
              <Link className="button" to={`/t/${active.id}`}>
                {t('group.toTournament')}
              </Link>
            ) : (
              <Link className="button" to={`/g/${group.id}/play`}>
                {t('group.assemble')}
              </Link>
            )}
          </div>
        )}
      </header>

      {active && showing && (
        <>
          <CourtGrid round={showing} totalRounds={active.total_rounds} />
          <Standings rows={active.standings} />
          <Climb progression={active.progression} />
        </>
      )}

      <section className="section" aria-labelledby="archive-heading">
        <div className="section-head">
          <h2 id="archive-heading">{t('group.archive')}</h2>
          <span className="eyebrow">{past.length}</span>
        </div>

        {past.length === 0 ? (
          <Note title={t('group.noneYet')}>
            {group.is_owner ? t('group.assembleFirst') : t('group.someoneWill')}
          </Note>
        ) : (
          <TournamentList entries={past} />
        )}
      </section>

      <Roster
        groupId={group.id}
        players={players}
        canEdit={group.is_owner}
        onChange={setRoster}
      />
    </>
  )
}
