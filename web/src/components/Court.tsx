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

import type { Match, Round } from '../lib/api'

/**
 * Court markings to scale: 20m long by 10m wide, service lines 3m either side of the net,
 * and the centre service line running back from each of them. Stretched to fit the box, so
 * the strokes are marked non-scaling to stay hairline-crisp at any size.
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
      {/* Service lines, 3m from the net on each side. */}
      <line x1="70" y1="0" x2="70" y2="100" {...line} opacity="0.35" />
      <line x1="130" y1="0" x2="130" y2="100" {...line} opacity="0.35" />
      {/* Centre service lines, splitting each pair of boxes. */}
      <line x1="0" y1="50" x2="70" y2="50" {...line} opacity="0.35" />
      <line x1="130" y1="50" x2="200" y2="50" {...line} opacity="0.35" />
      {/* The net. */}
      <line x1="100" y1="0" x2="100" y2="100" {...line} strokeWidth={2} opacity="0.9" />
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

function CourtBox({ match, index }: { match: Match; index: number }) {
  const played = match.score_a !== null && match.score_b !== null

  return (
    <figure
      className={`court enter${played ? '' : ' is-live'}`}
      style={{ animationDelay: `${index * 70}ms` }}
    >
      <Markings />
      <span className="court-tag">Корт {match.court}</span>
      {!played && <span className="court-live">Идёт</span>}
      <Side players={match.team_a} score={match.score_a} align="start" />
      <Side players={match.team_b} score={match.score_b} align="end" />
    </figure>
  )
}

export function CourtGrid({ round, totalRounds }: { round: Round; totalRounds: number }) {
  return (
    <section className="section" aria-labelledby="round-heading">
      <h2 className="round-meta" id="round-heading">
        <span className="round-number">{round.number}</span>
        <span className="round-of">
          раунд из {totalRounds}
          {round.complete ? ' · доигран' : ''}
        </span>
      </h2>
      <div className="courts">
        {round.matches.map((match, index) => (
          <CourtBox key={match.court} match={match} index={index} />
        ))}
      </div>
    </section>
  )
}
