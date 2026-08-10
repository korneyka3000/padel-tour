/**
 * The climb: what place everyone held, round by round.
 *
 * The obvious chart here — cumulative points — turns out to say almost nothing. Every player
 * gains between half and all of the match target each round, so eight lines rise in near
 * parallel and cross almost never. Places are where the story is: who overtook whom, and
 * when. That is also the whole point of a Mexicano, where your place decides who you play
 * next.
 *
 * Hand-drawn rather than charted by a library: the lines are meant to read as lanes, and a
 * library's defaults would have to be fought the whole way.
 */

import { useEffect, useId, useRef, useState } from 'react'

import type { PlayerProgress } from '../lib/api'
import { useT } from './Locale'

const ROW = 30
const PAD = { top: 20, right: 82, bottom: 24, left: 24 }
const FALLBACK_WIDTH = 640

/** Distinct enough to tell apart at a glance, all sitting inside the court palette. */
const LANE_COLOURS = [
  '#7FD4C8',
  '#FFB454',
  '#8FB8FF',
  '#F2A5C4',
  '#B9E36A',
  '#E8F4F2',
  '#63C6E8',
  '#C6A6F0',
  '#FF9E7A',
  '#9AD6A0',
  '#D8C77E',
  '#A7C0D6',
]

function laneColour(index: number): string {
  return LANE_COLOURS[index % LANE_COLOURS.length] ?? '#E8F4F2'
}

/**
 * The drawing is sized in CSS pixels rather than scaled from a fixed viewBox, so that 11px
 * of label is 11px on a phone as well as on a laptop. A fixed viewBox would shrink the type
 * to something unreadable at 390 wide.
 */
function useMeasuredWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(FALLBACK_WIDTH)

  useEffect(() => {
    const node = ref.current
    if (!node) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setWidth(Math.max(entry.contentRect.width, 260))
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  return [ref, width]
}

export function Climb({ progression }: { progression: PlayerProgress[] }) {
  const t = useT()
  const [active, setActive] = useState<string | null>(null)
  const [ref, width] = useMeasuredWidth()
  const titleId = useId()

  const lines = progression.filter((line) => line.points.length > 0)
  const rounds = lines[0]?.points.map((point) => point.round_no) ?? []
  const places = lines.length
  const height = PAD.top + PAD.bottom + Math.max(places - 1, 1) * ROW

  const step = (width - PAD.left - PAD.right) / Math.max(rounds.length - 1, 1)
  const x = (roundNo: number) => PAD.left + Math.max(rounds.indexOf(roundNo), 0) * step
  const y = (rank: number) => PAD.top + (rank - 1) * ROW

  return (
    <section className="section" aria-labelledby={titleId}>
      <div className="section-head">
        <h2 id={titleId}>{t('climb.title')}</h2>
        <span className="eyebrow">{t('climb.subtitle')}</span>
      </div>

      <div ref={ref}>
        {lines.length > 0 && (
          <svg
            className="climb"
            width={width}
            height={height}
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={t('climb.aria', { name: lines[0]?.name ?? '' })}
          >
            {rounds.map((roundNo) => (
              <g key={roundNo}>
                <line
                  className="climb-grid"
                  x1={x(roundNo)}
                  x2={x(roundNo)}
                  y1={PAD.top - 8}
                  y2={height - PAD.bottom + 4}
                />
                <text
                  className="climb-axis"
                  x={x(roundNo)}
                  y={height - 6}
                  textAnchor="middle"
                >
                  R{roundNo}
                </text>
              </g>
            ))}

            {Array.from({ length: places }, (_, index) => (
              <text
                key={index}
                className="climb-axis"
                x={PAD.left - 10}
                y={y(index + 1) + 4}
                textAnchor="end"
              >
                {index + 1}
              </text>
            ))}

            {lines.map((line, index) => {
              const colour = laneColour(index)
              const dimmed = active !== null && active !== line.player_id
              const path = line.points
                .map(
                  (point, at) =>
                    `${at === 0 ? 'M' : 'L'} ${x(point.round_no)} ${y(point.rank)}`,
                )
                .join(' ')
              const last = line.points[line.points.length - 1]

              return (
                <g
                  key={line.player_id}
                  className={`climb-row${dimmed ? ' is-dimmed' : ''}`}
                  onMouseEnter={() => setActive(line.player_id)}
                  onMouseLeave={() => setActive(null)}
                >
                  <path className="climb-line" d={path} stroke={colour} />
                  {line.points.map((point) => (
                    <circle
                      key={point.round_no}
                      className="climb-dot"
                      cx={x(point.round_no)}
                      cy={y(point.rank)}
                      r={3}
                      fill={colour}
                    />
                  ))}
                  {last && (
                    <text className="climb-label" x={x(last.round_no) + 9} y={y(last.rank) + 4}>
                      {line.name}
                    </text>
                  )}
                </g>
              )
            })}
          </svg>
        )}
      </div>

      {/* Hover is not available on the phones this is mostly read on. */}
      <div className="climb-legend">
        {lines.map((line, index) => (
          <button
            key={line.player_id}
            type="button"
            className="climb-chip"
            aria-pressed={active === line.player_id}
            style={
              active === line.player_id
                ? {
                    background: laneColour(index),
                    borderColor: laneColour(index),
                    color: 'var(--night)',
                  }
                : { borderColor: laneColour(index) }
            }
            onClick={() => setActive(active === line.player_id ? null : line.player_id)}
          >
            {line.name}
          </button>
        ))}
      </div>
    </section>
  )
}
