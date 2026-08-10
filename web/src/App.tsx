import { Analytics } from '@vercel/analytics/react'
import { useEffect } from 'react'
import { BrowserRouter, Route, Routes, useNavigate } from 'react-router'

import { Note } from './components/Async'
import { LocaleProvider, useT } from './components/Locale'
import { SessionProvider } from './components/SessionProvider'
import { TopBar } from './components/TopBar'
import { launchDestination, webApp } from './lib/telegram'
import { DrawPage } from './pages/DrawPage'
import { EnterPage } from './pages/EnterPage'
import { GroupPage } from './pages/GroupPage'
import { HomePage } from './pages/HomePage'
import { InvitePage } from './pages/InvitePage'
import { PlayerPage } from './pages/PlayerPage'
import { SignInPage } from './pages/SignInPage'
import { TournamentPage } from './pages/TournamentPage'

export function App() {
  return (
    <BrowserRouter>
      {/* Language outside the session: a sign-in page has to be readable before there is
          anybody to have a preference. */}
      <LocaleProvider>
        <SessionProvider>
          <LaunchRedirect />
          <main className="shell">
            <TopBar />
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/sign-in" element={<SignInPage />} />
              <Route path="/auth/enter" element={<EnterPage />} />
              <Route path="/i/:token" element={<InvitePage />} />
              <Route path="/g/:id" element={<GroupPage />} />
              <Route path="/g/:id/play" element={<DrawPage />} />
              <Route path="/t/:id" element={<TournamentPage />} />
              <Route path="/p/:id" element={<PlayerPage />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </main>
          {/* Cookieless, and it sends nothing we choose — page paths and referrers only.
              Inside the router so route changes count as visits; outside it the component
              would only ever see the first page somebody landed on. */}
          <Analytics />
        </SessionProvider>
      </LocaleProvider>
    </BrowserRouter>
  )
}

function NotFound() {
  const t = useT()
  return <Note title={t('notFound.title')}>{t('notFound.body')}</Note>
}

/**
 * Where a Mini App launch was pointed.
 *
 * A chat opens the app with `?startapp=t_<uuid>`, which is the only parameter Telegram
 * passes through — so it is read once, on the way in, and turned into a route. Once only:
 * after that the person is navigating, and sending them back to the launch destination on
 * every render would trap them on it.
 */
function LaunchRedirect() {
  const navigate = useNavigate()

  useEffect(() => {
    const param = webApp()?.initDataUnsafe?.start_param
    if (!param) return
    const destination = launchDestination(param)
    if (destination !== '/') void navigate(destination, { replace: true })
  }, [navigate])

  return null
}
