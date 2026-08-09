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
import { api, plural } from '../lib/api'

/** A round needs four people on a court, and an Americano needs whole courts. */
const PER_COURT = 4

const POINTS = [16, 21, 24, 32]

const PATTERNS: { value: PairingPattern; label: string; hint: string }[] = [
  { value: 'crossover', label: 'Крест', hint: '1+4 против 2+3' },
  { value: 'split', label: 'Через одного', hint: '1+3 против 2+4' },
  { value: 'top_heavy', label: 'По силе', hint: '1+2 против 3+4' },
]

const DEFAULT_ROUNDS = 5

export function DrawPage() {
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
  if (error) return <Failed message={error} />
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
      setFailure(problem instanceof Error ? problem.message : 'Не собралось')
      setBusy(false)
    }
  }

  return (
    <>
      <a className="back" href={`/g/${id}`}>
        ← К группе
      </a>

      <header>
        <p className="eyebrow">{data.name}</p>
        <h1 className="title">Собрать турнир</h1>
        <p className="subtitle">
          {count === 0
            ? 'Отметьте, кто играет'
            : `${count} ${plural(count, 'игрок', 'игрока', 'игроков')}${
                fits ? ` · ${courts} ${plural(courts, 'корт', 'корта', 'кортов')}` : ''
              }`}
        </p>
      </header>

      <section className="section" aria-labelledby="who-heading">
        <div className="section-head">
          <h2 id="who-heading">Кто играет</h2>
          {!fits && count > 0 && (
            <span className="eyebrow">нужно 4, 8, 12, 16…</span>
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
          <h2 id="rules-heading">Правила</h2>
        </div>

        <Choice
          label="Формат"
          options={[
            { value: 'americano', label: 'Американо', hint: 'каждый с каждым в паре' },
            { value: 'mexicano', label: 'Мексикано', hint: 'пары по таблице' },
          ]}
          value={format}
          onChange={setFormat}
        />

        <Choice
          label="Матч до"
          options={POINTS.map((value) => ({ value, label: String(value) }))}
          value={points}
          onChange={setPoints}
        />

        {format === 'mexicano' && (
          <>
            <Choice label="Пары" options={PATTERNS} value={pattern} onChange={setPattern} />
            <label className="field">
              <span className="field-label">Раундов</span>
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
          {busy ? 'Жеребьёвка…' : 'Жеребьёвка'}
        </button>
        {failure && <p className="field-error">{failure}</p>}
      </div>
    </>
  )
}

function Choice<T extends string | number>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: { value: T; label: string; hint?: string }[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <fieldset className="choice">
      <legend className="field-label">{label}</legend>
      <div className="choice-options">
        {options.map((option) => (
          <button
            className={`pick${option.value === value ? ' is-picked' : ''}`}
            key={String(option.value)}
            type="button"
            aria-pressed={option.value === value}
            onClick={() => onChange(option.value)}
          >
            {option.label}
            {option.hint && <span className="pick-hint">{option.hint}</span>}
          </button>
        ))}
      </div>
    </fieldset>
  )
}
