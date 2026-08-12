/**
 * A round, drawn as the courts it is played on.
 *
 * A padel court is a glass box twenty metres by ten with the net across the middle, and that
 * shape is the most recognisable thing in the sport. Drawing it means someone standing on
 * court can glance at their phone and find themselves, rather than parsing a line of text.
 *
 * Turned side-on — net vertical, pairs left and right — for two reasons. It is the same
 * geometry either way, and a 2:1 landscape box fits a phone where a 1:2 portrait one would
 * make every round a scroll.
 */

import { useState } from 'react'

import type { Match, Round } from '../lib/api'
import { useT } from './Locale'

//: The net, in viewBox units. One unit is 10cm, so the box is the court: 20m by 10m.
const NET = 100

//: Distance from the net to the service line — 6.95m, which is what makes this padel.
//:
//: It was 3m, and drawn from the wrong end: the centre line ran through the *back* of each
//: half instead of the front. The result read as a tennis court to anyone who plays, which
//: is everyone looking at this screen. Tennis puts its service line at 6.4m and fills the
//: rest of the half with tramlines; padel has no tramlines and leaves a bare 3.05m strip
//: between the service line and the back glass, where the ball is played off the wall.
const SERVICE = 69.5

/**
 * Padel court markings to scale, seen from above with the net vertical.
 *
 * Five lines, which is all a padel court has. Nothing marks the walls, because the card's
 * own border is already the glass box — an attempt at drawing where the glass gives way to
 * mesh just added two ticks nobody could read.
 *
 * Stretched to fit the box, so the strokes are marked non-scaling to stay hairline-crisp at
 * any size.
 */
function Markings() {
  const line = {
    stroke: 'currentColor',
    strokeWidth: 1,
    vectorEffect: 'non-scaling-stroke' as const,
  }
  return (
    <svg
      className="court-lines"
      viewBox="0 0 200 100"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      {/* Service lines, 6.95m from the net on each side. */}
      <line x1={NET - SERVICE} y1="0" x2={NET - SERVICE} y2="100" {...line} opacity="0.35" />
      <line x1={NET + SERVICE} y1="0" x2={NET + SERVICE} y2="100" {...line} opacity="0.35" />
      {/* Centre service lines: net to service line, never into the back strip. */}
      <line x1={NET - SERVICE} y1="50" x2={NET} y2="50" {...line} opacity="0.35" />
      <line x1={NET} y1="50" x2={NET + SERVICE} y2="50" {...line} opacity="0.35" />
      {/* The net. */}
      <line x1={NET} y1="0" x2={NET} y2="100" {...line} strokeWidth={2} opacity="0.9" />
    </svg>
  )
}

function Side({
  players,
  score,
  align,
}: {
  players: [string, string]
  score: number | null
  align: 'start' | 'end'
}) {
  return (
    <div className={`side side-${align}`}>
      {score !== null && <span className="side-score">{score}</span>}
      <span className="side-players">
        {players.map((name) => (
          <span className="player" key={name}>
            {name}
          </span>
        ))}
      </span>
    </div>
  )
}

/**
 * Entering a result: one number, not two.
 *
 * A match runs to a fixed total, so the two scores are one fact — type either side and the
 * other follows. Two independent boxes would let someone enter a sum the rules forbid and
 * find out about it from the server, after the network, having already looked away.
 */
function ScoreEntry({
  match,
  points,
  onSubmit,
}: {
  match: Match
  points: number
  onSubmit: (a: number, b: number) => Promise<void>
}) {
  const t = useT()
  const [open, setOpen] = useState(match.score_a === null)
  const [a, setA] = useState<number | null>(match.score_a)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  if (!open) {
    return (
      <div className="court-score">
        <button className="link-button" type="button" onClick={() => setOpen(true)}>
          {t('court.fixScore')}
        </button>
      </div>
    )
  }

  const b = a === null ? null : points - a
  const ready = a !== null && a >= 0 && a <= points

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (a === null || b === null) return
    setBusy(true)
    setError(null)
    try {
      await onSubmit(a, b)
      setOpen(false)
    } catch (failure) {
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="court-score" onSubmit={submit}>
      <input
        className="score-input"
        type="number"
        inputMode="numeric"
        min={0}
        max={points}
        value={a ?? ''}
        aria-label={t('court.pointsFor', { pair: match.team_a.join(' + ') })}
        onChange={(event) =>
          setA(event.target.value === '' ? null : Number(event.target.value))
        }
      />
      <span className="score-colon">:</span>
      <input
        className="score-input"
        type="number"
        inputMode="numeric"
        min={0}
        max={points}
        value={b ?? ''}
        aria-label={t('court.pointsFor', { pair: match.team_b.join(' + ') })}
        onChange={(event) =>
          setA(event.target.value === '' ? null : points - Number(event.target.value))
        }
      />
      <button className="button button-small" type="submit" disabled={!ready || busy}>
        {busy ? '…' : t('court.ok')}
      </button>
      {error && <span className="field-error">{error}</span>}
    </form>
  )
}

function CourtBox({
  match,
  index,
  scoring,
}: {
  match: Match
  index: number
  scoring?: Scoring
}) {
  const t = useT()
  const played = match.score_a !== null && match.score_b !== null
  const mine = scoring?.can(match) ?? false

  // Entry sits below the court rather than on it. The box is a fixed 2:1 with four names
  // already in it; a row of inputs laid over that lands on top of the near pair, and on a
  // phone there is no room to move it anywhere that is not on top of something.
  return (
    <div className="court-cell">
      <figure
        className={`court enter${played ? '' : ' is-live'}`}
        style={{ animationDelay: `${index * 70}ms` }}
      >
        <Markings />
        <span className="court-tag">{t('court.number', { court: match.court })}</span>
        {!played && <span className="court-live">{t('court.live')}</span>}
        <Side players={match.team_a} score={match.score_a} align="start" />
        <Side players={match.team_b} score={match.score_b} align="end" />
      </figure>
      {scoring && mine && (
        <ScoreEntry
          match={match}
          points={scoring.points}
          onSubmit={(a, b) => scoring.submit(match.court, a, b)}
        />
      )}
    </div>
  )
}

/** What a court needs in order to be scored from this screen. Absent means read-only. */
export interface Scoring {
  /** The match target, so the second number follows from the first. */
  points: number
  /** Mirrors the server's rule — see `canScore` in lib/api. */
  can: (match: Match) => boolean
  submit: (court: number, a: number, b: number) => Promise<void>
}

/** Stepping between rounds that have already been drawn. */
export interface RoundNav {
  onStep: (delta: number) => void
  canGoBack: boolean
  canGoForward: boolean
}

export function CourtGrid({
  round,
  totalRounds,
  scoring,
  nav,
}: {
  round: Round
  totalRounds: number
  scoring?: Scoring
  nav?: RoundNav
}) {
  const t = useT()

  return (
    <section className="section" aria-labelledby="round-heading">
      <h2 className="round-meta" id="round-heading">
        <span className="round-number">{round.number}</span>
        <span className="round-of">
          {t('court.roundOf', { total: totalRounds })}
          {round.complete ? ` · ${t('court.roundDone')}` : ''}
        </span>
        {nav && (
          // A score entered wrong is usually noticed a round later, so getting back to it
          // has to be possible from here — otherwise "correct a mistake" means asking
          // somebody with Telegram to do it.
          <span className="round-nav">
            <button
              className="link-button"
              type="button"
              disabled={!nav.canGoBack}
              aria-label={t('court.prevRound')}
              onClick={() => nav.onStep(-1)}
            >
              ←
            </button>
            <button
              className="link-button"
              type="button"
              disabled={!nav.canGoForward}
              aria-label={t('court.nextRound')}
              onClick={() => nav.onStep(1)}
            >
              →
            </button>
          </span>
        )}
      </h2>
      <div className="courts">
        {round.matches.map((match, index) => (
          // Keyed by round as well as court. Court 1 in round 2 is a different match than
          // court 1 in round 1, and keyed by court alone React reuses the score form — so
          // the next round opens already showing the previous round's score as entered.
          <CourtBox
            key={`${round.number}-${match.court}`}
            match={match}
            index={index}
            scoring={scoring}
          />
        ))}
      </div>
    </section>
  )
}
