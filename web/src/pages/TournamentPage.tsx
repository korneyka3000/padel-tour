/** One tournament: where play has got to, the table, the climb — and running it. */

import { useState } from 'react'
import { Link, useParams } from 'react-router'

import { Failed, Loading, useAsync } from '../components/Async'
import { Climb } from '../components/Climb'
import { CourtGrid } from '../components/Court'
import { Standings } from '../components/Standings'
import type { Scoring } from '../components/Court'
import type { Tournament } from '../lib/api'
import { useT } from '../components/Locale'
import { api, canScore } from '../lib/api'

export function TournamentPage() {
  const t = useT()
  const { id = '' } = useParams()
  const { data, error, loading } = useAsync(() => api.tournament(id), [id])
  // Every write answers with the whole tournament, so the screen is redrawn from the
  // server's own copy rather than from a guess about what the write changed.
  const [live, setLive] = useState<Tournament | null>(null)
  // Which round is on screen. Null means "wherever play has got to", which is what someone
  // standing on court wants; a number means they have stepped back to correct something.
  const [looking, setLooking] = useState<number | null>(null)

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />
  if (!data) return null

  const tournament = live ?? data
  // Where play has got to, unless the reader has stepped back to fix something.
  const current = tournament.rounds.findIndex((round) => !round.complete)
  const at = looking ?? (current === -1 ? tournament.rounds.length - 1 : current)
  const showing = tournament.rounds[at]
  const players = tournament.standings.length

  const scoring: Scoring | undefined =
    tournament.finished || !showing
      ? undefined
      : {
          points: tournament.points_per_match,
          can: (match) => canScore(tournament.viewer, match),
          submit: async (court, a, b) => {
            setLive(await api.putScore(tournament.id, showing.number, court, a, b))
          },
        }

  return (
    <>
      <Link className="back" to={`/g/${tournament.group_id}`}>
        {t('nav.toGroup')}
      </Link>

      <header>
        <p className="eyebrow">
          {tournament.finished ? t('tournament.finished') : t('tournament.live')} ·{' '}
          {t.date(tournament.created_at)}
        </p>
        <h1 className="title">{t(`format.${tournament.format}`)}</h1>
        <p className="subtitle">
          {t.count('players', players)} ·{' '}
          {t('tournament.matchTo', { points: tournament.points_per_match })} ·{' '}
          {t.count('rounds', tournament.total_rounds)}
        </p>
      </header>

      <Controls tournament={tournament} onChange={setLive} />

      {showing && (
        <CourtGrid
          round={showing}
          totalRounds={tournament.total_rounds}
          scoring={scoring}
          nav={
            tournament.rounds.length > 1
              ? {
                  onStep: (delta) => setLooking(at + delta),
                  canGoBack: at > 0,
                  canGoForward: at < tournament.rounds.length - 1,
                }
              : undefined
          }
        />
      )}

      <Standings rows={tournament.standings} />

      <Climb progression={tournament.progression} />
    </>
  )
}

/**
 * What the organiser can do to the tournament as a whole.
 *
 * Drawing the next round is offered to any member, not just the organiser, and the server
 * agrees: the next round follows from the standing and nobody chooses anything, so whoever
 * enters the last score of a round should not have to wait for someone else to press this.
 */
function Controls({
  tournament,
  onChange,
}: {
  tournament: Tournament
  onChange: (tournament: Tournament) => void
}) {
  const t = useT()
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const { viewer } = tournament
  const started = tournament.rounds.some((round) =>
    round.matches.some((match) => match.score_a !== null),
  )
  const roundsDrawn = tournament.rounds.length
  const currentComplete = tournament.rounds.at(-1)?.complete ?? false
  const canAdvance =
    !tournament.finished && currentComplete && roundsDrawn < tournament.total_rounds

  async function run(what: string, action: () => Promise<Tournament>) {
    setBusy(what)
    setError(null)
    try {
      onChange(await action())
    } catch (failure) {
      setError(t.say(failure))
    } finally {
      setBusy(null)
    }
  }

  if (tournament.finished || !viewer.is_member) return null

  const buttons = [
    canAdvance && {
      key: 'next',
      label: t('tournament.nextRound'),
      run: () => api.nextRound(tournament.id),
    },
    viewer.is_organiser &&
      !started && {
        key: 'reroll',
        label: t('tournament.reroll'),
        run: () => api.reroll(tournament.id),
      },
    viewer.is_organiser && {
      key: 'finish',
      label: t('tournament.finish'),
      run: () => api.finish(tournament.id),
    },
  ].filter((entry) => entry !== false && entry !== undefined)

  if (buttons.length === 0) return null

  return (
    <div className="actions">
      {buttons.map((button) => (
        <button
          className="button button-quiet"
          key={button.key}
          type="button"
          disabled={busy !== null}
          onClick={() => void run(button.key, button.run)}
        >
          {busy === button.key ? '…' : button.label}
        </button>
      ))}
      {error && <p className="field-error">{error}</p>}
    </div>
  )
}
