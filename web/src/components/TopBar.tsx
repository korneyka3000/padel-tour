/** The one place on every page that says whether anybody is signed in. */

import { Link } from 'react-router'

import { api } from '../lib/api'
import { rememberDestination, useSession } from '../lib/auth'

export function TopBar() {
  const { me, loading, refresh } = useSession()

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
          Выйти
        </button>
      ) : (
        <Link
          className="link-button"
          to="/sign-in"
          onClick={() => rememberDestination(window.location.pathname)}
        >
          Войти
        </Link>
      )}
    </nav>
  )
}
