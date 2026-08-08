import { BrowserRouter, Route, Routes } from 'react-router'

import { Note } from './components/Async'
import { GroupPage } from './pages/GroupPage'
import { HomePage } from './pages/HomePage'
import { PlayerPage } from './pages/PlayerPage'
import { TournamentPage } from './pages/TournamentPage'

export function App() {
  return (
    <BrowserRouter>
      <main className="shell">
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/g/:id" element={<GroupPage />} />
          <Route path="/t/:id" element={<TournamentPage />} />
          <Route path="/p/:id" element={<PlayerPage />} />
          <Route
            path="*"
            element={<Note title="Такой страницы нет">Проверьте ссылку.</Note>}
          />
        </Routes>
      </main>
    </BrowserRouter>
  )
}
