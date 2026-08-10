/**
 * Assembling a tournament: who is playing, and under what rules.
 *
 * The counts an Americano allows are a property of the schedule, not a preference, so the
 * screen says which ones work before the draw is attempted rather than letting the server
 * refuse a form that looked fine.
 */

import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'

import { Failed, Loading, useAsync } from '../components/Async'
import type { Format, PairingPattern } from '../lib/api'
import type { Key } from '../lib/i18n'
import { ru } from '../lib/i18n'
import { useT } from '../components/Locale'
import { api } from '../lib/api'

/** A round needs four people on a court, and an Americano needs whole courts. */
const PER_COURT = 4

const POINTS = [16, 21, 24, 32]

/** Keyed rather than worded: the pattern is data, its name is language. */
const PATTERNS: { value: PairingPattern; label: Key; hint: Key }[] = [
  { value: 'crossover', label: 'draw.crossover', hint: 'draw.crossoverHint' },
  { value: 'split', label: 'draw.split', hint: 'draw.splitHint' },
  { value: 'top_heavy', label: 'draw.topHeavy', hint: 'draw.topHeavyHint' },
]

const DEFAULT_ROUNDS = 5

export function DrawPage() {
  const t = useT()
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { data, error, loading } = useAsync(() => api.group(id), [id])

  const [picked, setPicked] = useState<Set<string>>(new Set())
  const [format, setFormat] = useState<Format>('americano')
  const [points, setPoints] = useState(24)
  const [pattern, setPattern] = useState<PairingPattern>('crossover')
  const [rounds, setRounds] = useState(DEFAULT_ROUNDS)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)

  if (loading) return <Loading />
  if (error) return <Failed failure={error} />
  if (!data) return null

  function toggle(playerId: string) {
    setPicked((current) => {
      const next = new Set(current)
      if (!next.delete(playerId)) next.add(playerId)
      return next
    })
  }

  const count = picked.size
  const fits = count >= PER_COURT && count % PER_COURT === 0
  const courts = Math.floor(count / PER_COURT)

  async function submit() {
    setBusy(true)
    setFailure(null)
    try {
      const drawn = await api.draw(id, {
        player_ids: [...picked],
        format,
        points_per_match: points,
        pairing_pattern: pattern,
        rounds: format === 'mexicano' ? rounds : null,
      })
      void navigate(`/t/${drawn.id}`)
    } catch (problem) {
      setFailure(t.say(problem))
      setBusy(false)
    }
  }

  return (
    <>
      <a className="back" href={`/g/${id}`}>
        {t('nav.toGroup')}
      </a>

      <header>
        <p className="eyebrow">{data.name}</p>
        <h1 className="title">{t('draw.title')}</h1>
        <p className="subtitle">
          {count === 0
            ? t('draw.pickWho')
            : `${t.count('players', count)}${fits ? ` · ${t.count('courts', courts)}` : ''}`}
        </p>
      </header>

      <section className="section" aria-labelledby="who-heading">
        <div className="section-head">
          <h2 id="who-heading">{t('draw.whoPlays')}</h2>
          {!fits && count > 0 && (
            <span className="eyebrow">{t('draw.needMultiple')}</span>
          )}
        </div>
        <ul className="picks">
          {data.players.map((player) => (
            <li key={player.id}>
              <button
                className={`pick${picked.has(player.id) ? ' is-picked' : ''}`}
                type="button"
                aria-pressed={picked.has(player.id)}
                onClick={() => toggle(player.id)}
              >
                {player.name}
              </button>
            </li>
          ))}
        </ul>
      </section>

      <section className="section" aria-labelledby="rules-heading">
        <div className="section-head">
          <h2 id="rules-heading">{t('draw.rules')}</h2>
        </div>

        <Choice
          label="draw.format"
          options={[
            { value: 'americano', label: 'format.americano', hint: 'draw.americanoHint' },
            { value: 'mexicano', label: 'format.mexicano', hint: 'draw.mexicanoHint' },
          ]}
          value={format}
          onChange={setFormat}
        />

        <Choice
          label="draw.matchTo"
          options={POINTS.map((value) => ({ value, label: String(value) }))}
          value={points}
          onChange={setPoints}
        />

        {format === 'mexicano' && (
          <>
            <Choice label="draw.pairs" options={PATTERNS} value={pattern} onChange={setPattern} />
            <label className="field">
              <span className="field-label">{t('draw.rounds')}</span>
              <input
                className="field-input"
                type="number"
                inputMode="numeric"
                min={1}
                max={40}
                value={rounds}
                onChange={(event) => setRounds(Number(event.target.value))}
              />
            </label>
          </>
        )}
      </section>

      <div className="actions">
        <button
          className="button"
          type="button"
          disabled={!fits || busy}
          onClick={() => void submit()}
        >
          {busy ? t('draw.going') : t('draw.go')}
        </button>
        {failure && <p className="field-error">{failure}</p>}
      </div>
    </>
  )
}

/**
 * Options carry keys, not words — except the numbers, which are the same in every language
 * and would need a dictionary entry each to pretend otherwise.
 */
function Choice<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: Key
  options: { value: T; label: Key | string; hint?: Key }[]
  value: T
  onChange: (value: T) => void
}) {
  const t = useT()
  const say = (word: Key | string) => (word in ru ? t(word as Key) : word)

  return (
    <fieldset className="choice">
      <legend className="field-label">{t(label)}</legend>
      <div className="choice-options">
        {options.map((option) => (
          <button
            className={`pick${option.value === value ? ' is-picked' : ''}`}
            key={String(option.value)}
            type="button"
            aria-pressed={option.value === value}
            onClick={() => onChange(option.value)}
          >
            {say(option.label)}
            {option.hint && <span className="pick-hint">{t(option.hint)}</span>}
          </button>
        ))}
      </div>
    </fieldset>
  )
}
