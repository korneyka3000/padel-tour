import { BrowserRouter, Route, Routes } from 'react-router'

import { Note } from './components/Async'
import { SessionProvider } from './components/SessionProvider'
import { TopBar } from './components/TopBar'
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
      <SessionProvider>
        <main className="shell">
          <TopBar />
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/sign-in" element={<SignInPage />} />
            <Route path="/auth/enter" element={<EnterPage />} />
            <Route path="/i/:token" element={<InvitePage />} />
            <Route path="/g/:id" element={<GroupPage />} />
            <Route path="/t/:id" element={<TournamentPage />} />
            <Route path="/p/:id" element={<PlayerPage />} />
            <Route
              path="*"
              element={<Note title="Такой страницы нет">Проверьте ссылку.</Note>}
            />
          </Routes>
        </main>
      </SessionProvider>
    </BrowserRouter>
  )
}
