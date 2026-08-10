import { BrowserRouter, Route, Routes } from 'react-router'

import { Note } from './components/Async'
import { LocaleProvider, useT } from './components/Locale'
import { SessionProvider } from './components/SessionProvider'
import { TopBar } from './components/TopBar'
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
        </SessionProvider>
      </LocaleProvider>
    </BrowserRouter>
  )
}

function NotFound() {
  const t = useT()
  return <Note title={t('notFound.title')}>{t('notFound.body')}</Note>
}
