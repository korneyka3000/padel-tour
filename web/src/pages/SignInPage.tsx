/**
 * Signing in.
 *
 * One field, because there is no password and there is not going to be one. The screen after
 * submitting says what to do next and nothing else — whether the address is known is not
 * ours to reveal, and the server answers the same either way.
 */

import { useState } from 'react'
import { Link } from 'react-router'

import { api } from '../lib/api'

export function SignInPage() {
  const [email, setEmail] = useState('')
  const [sent, setSent] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      await api.askForLink(email)
      setSent(true)
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Не отправилось')
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <>
        <Link className="back" to="/">
          ← На главную
        </Link>
        <header>
          <p className="eyebrow">Вход</p>
          <h1 className="title">Проверьте почту</h1>
          <p className="subtitle">
            Отправили ссылку на <b>{email}</b>. Она действует пятнадцать минут и срабатывает
            один раз.
          </p>
        </header>
      </>
    )
  }

  return (
    <>
      <Link className="back" to="/">
        ← На главную
      </Link>
      <header>
        <p className="eyebrow">Вход</p>
        <h1 className="title">Ссылка вместо пароля</h1>
        <p className="subtitle">
          Оставьте адрес — пришлём ссылку, по которой вы окажетесь внутри. Пароля здесь нет.
        </p>
      </header>

      <form className="form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">Почта</span>
          <input
            className="field-input"
            type="email"
            name="email"
            autoComplete="email"
            required
            placeholder="anya@example.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <button className="button" type="submit" disabled={busy || email.length === 0}>
          {busy ? 'Отправляем…' : 'Прислать ссылку'}
        </button>
        {error && <p className="field-error">{error}</p>}
      </form>
    </>
  )
}
