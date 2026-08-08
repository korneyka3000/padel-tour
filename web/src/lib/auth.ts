/**
 * Who is signed in, for the whole app.
 *
 * The session is a cookie the script cannot read, so the only way to answer the question is
 * to ask the server. That happens once on load; everything after it reads from here.
 */

import { createContext, useContext } from 'react'

import type { Me } from './api'

export interface Session {
  me: Me | null
  loading: boolean
  /** Re-ask the server. Called after signing in, out, or accepting an invitation. */
  refresh: () => Promise<void>
}

export const SessionContext = createContext<Session>({
  me: null,
  loading: true,
  refresh: async () => {},
})

export function useSession(): Session {
  return useContext(SessionContext)
}

/**
 * Where to go once signed in.
 *
 * A sign-in link arrives by email and lands on a page of its own, which loses whatever the
 * person was trying to do. Parking that here — rather than in the link — keeps the token in
 * the email from carrying a destination anyone could set.
 */
const AFTER_SIGN_IN = 'padel:after-sign-in'

export function rememberDestination(path: string): void {
  sessionStorage.setItem(AFTER_SIGN_IN, path)
}

export function takeDestination(): string {
  const path = sessionStorage.getItem(AFTER_SIGN_IN)
  sessionStorage.removeItem(AFTER_SIGN_IN)
  // Only a path of ours: an absolute URL here would be an open redirect.
  return path && path.startsWith('/') && !path.startsWith('//') ? path : '/'
}
