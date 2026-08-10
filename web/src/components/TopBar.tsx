/** The one place on every page that says whether anybody is signed in. */

import { Link } from 'react-router'

import { api } from '../lib/api'
import { useLocaleChoice, useT } from './Locale'
import { LOCALES, LOCALE_LABEL } from '../lib/i18n'
import { rememberDestination, useSession } from '../lib/auth'

export function TopBar() {
  const { me, loading, refresh } = useSession()
  const t = useT()

  async function signOut() {
    await api.signOut()
    await refresh()
  }

  return (
    <nav className="topbar">
      <Link className="brand" to="/">
        Padel<span>Tour</span>
      </Link>
      {loading ? null : me ? (
        <button className="link-button" type="button" onClick={() => void signOut()}>
          {t('nav.signOut')}
        </button>
      ) : (
        <Link
          className="link-button"
          to="/sign-in"
          onClick={() => rememberDestination(window.location.pathname)}
        >
          {t('nav.signIn')}
        </Link>
      )}
      <LanguageSwitch />
    </nav>
  )
}

/**
 * Two buttons rather than a select. With two languages a dropdown hides the choice behind
 * a click, and the whole thing fits in the space the arrow would have taken.
 */
function LanguageSwitch() {
  const { locale, choose } = useLocaleChoice()
  const t = useT()

  return (
    <span className="langs" role="group" aria-label={t('nav.language')}>
      {LOCALES.map((one) => (
        <button
          className="link-button"
          key={one}
          type="button"
          aria-pressed={one === locale}
          onClick={() => choose(one)}
        >
          {LOCALE_LABEL[one]}
        </button>
      ))}
    </span>
  )
}
