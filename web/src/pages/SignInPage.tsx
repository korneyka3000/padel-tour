/**
 * Signing in.
 *
 * One field, because there is no password and there is not going to be one. The screen after
 * submitting says what to do next and nothing else — whether the address is known is not
 * ours to reveal, and the server answers the same either way.
 */

import { useState } from 'react'
import { Link } from 'react-router'

import { useT } from '../components/Locale'

import { api } from '../lib/api'

export function SignInPage() {
  const t = useT()
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
      setError(t.say(failure))
    } finally {
      setBusy(false)
    }
  }

  if (sent) {
    return (
      <>
        <Link className="back" to="/">
          {t('nav.home')}
        </Link>
        <header>
          <p className="eyebrow">{t('signIn.eyebrow')}</p>
          <h1 className="title">{t('signIn.checkMail')}</h1>
          <p className="subtitle">
            {t('signIn.sentTo', { email })}
          </p>
        </header>
      </>
    )
  }

  return (
    <>
      <Link className="back" to="/">
        {t('nav.home')}
      </Link>
      <header>
        <p className="eyebrow">{t('signIn.eyebrow')}</p>
        <h1 className="title">{t('signIn.title')}</h1>
        <p className="subtitle">
          {t('signIn.body')}
        </p>
      </header>

      <form className="form" onSubmit={submit}>
        <label className="field">
          <span className="field-label">{t('signIn.emailLabel')}</span>
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
          {busy ? t('signIn.sending') : t('signIn.send')}
        </button>
        {error && <p className="field-error">{error}</p>}
      </form>
    </>
  )
}
