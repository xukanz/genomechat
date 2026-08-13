import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { MainLayout } from '../components/layout/MainLayout'
import { ChatPage } from '../pages/ChatPage'
import LoginPage from '../pages/LoginPage'
import { AboutPage } from '../pages/AboutPage'
import { useAuthStore } from '../store/authStore'
import { DEMO_CREDENTIALS } from './mockData'

/**
 * Router for the demo build.
 *
 * Mirrors the real `App.tsx` route shape (landing → login → chat behind a
 * ProtectedRoute) using the same page components, so each screen is identical
 * to production. Two deliberate differences:
 *
 * - `HashRouter`, not `BrowserRouter`: this bundle is served at `/demo.html`,
 *   so path-based routes would be resolved against the main app by the server.
 * - `/login` is pre-filled with demo credentials, and `/register` redirects to
 *   it (no registration flow in the demo).
 *
 * The chat route is `/app` because `LoginForm` hard-codes that redirect target.
 */
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isAuthenticated } = useAuthStore()

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return <>{children}</>
}

export function DemoApp() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<AboutPage />} />
        <Route path="/about" element={<AboutPage />} />
        <Route
          path="/login"
          element={
            <LoginPage
              defaultEmail={DEMO_CREDENTIALS.email}
              defaultPassword={DEMO_CREDENTIALS.password}
            />
          }
        />
        <Route path="/register" element={<Navigate to="/login" replace />} />

        <Route
          element={
            <ProtectedRoute>
              <MainLayout />
            </ProtectedRoute>
          }
        >
          <Route path="/app" element={<ChatPage />} />
          <Route path="/app/chat/:chatId" element={<ChatPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </HashRouter>
  )
}
