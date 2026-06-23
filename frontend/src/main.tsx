import React, { useState } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import FarmerPage from './pages/FarmerPage'
import YoungPage from './pages/YoungPage'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import { getToken, clearToken } from './api'
import './style.css'

function RequireAuth({ children }: { children: React.ReactNode }) {
  if (!getToken()) return <Navigate to="/login" replace />
  return <>{children}</>
}

function NavLinks({ loc, loggedIn, onLogout, onNavigate }: {
  loc: ReturnType<typeof useLocation>
  loggedIn: boolean
  onLogout: () => void
  onNavigate?: () => void
}) {
  const isActive = (path: string) => loc.pathname === path ? 'active' : ''
  return (
    <>
      <Link to="/#features" onClick={onNavigate}>서비스 소개</Link>
      <Link to="/#steps" onClick={onNavigate}>작동 방식</Link>
      <Link className={isActive('/farmer')} to="/farmer" onClick={onNavigate}>농가 등록</Link>
      <Link className={isActive('/young')} to="/young" onClick={onNavigate}>청년농 매칭</Link>
      <span className="lp-nav-divider" aria-hidden="true" />
      {loggedIn ? (
        <>
          <Link className={isActive('/dashboard')} to="/dashboard" onClick={onNavigate}>내 농장</Link>
          <a href="#" onClick={e => { e.preventDefault(); onLogout(); onNavigate?.() }}>로그아웃</a>
        </>
      ) : (
        <Link className={isActive('/login')} to="/login" onClick={onNavigate}>로그인</Link>
      )}
    </>
  )
}

function Nav() {
  const loc = useLocation()
  const navigate = useNavigate()
  const loggedIn = !!getToken()
  const [mobileOpen, setMobileOpen] = useState(false)

  const logout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <nav className="lp-nav">
      <div className="lp-wrap lp-nav-inner">
        <Link className="lp-logo" to="/" style={{ color: '#fff' }} onClick={() => setMobileOpen(false)}>
          <span className="mark"><i></i></span>팜바톤
        </Link>
        <div className="lp-nav-links">
          <NavLinks loc={loc} loggedIn={loggedIn} onLogout={logout} />
        </div>
        <div className="lp-nav-right">
          {loc.pathname !== '/farmer' && (
            <Link className="lp-pill lp-pill-lime" to="/farmer">시작하기 →</Link>
          )}
          <button
            className="lp-nav-burger"
            aria-label="메뉴"
            onClick={() => setMobileOpen(o => !o)}
          >
            {mobileOpen ? (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 6l12 12M18 6L6 18" /></svg>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
            )}
          </button>
        </div>
      </div>
      {mobileOpen && (
        <div className="lp-nav-mobile-panel">
          <NavLinks loc={loc} loggedIn={loggedIn} onLogout={logout} onNavigate={() => setMobileOpen(false)} />
        </div>
      )}
    </nav>
  )
}

function App() {
  const loc = useLocation()
  const isLanding = loc.pathname === '/'

  return (
    <>
      <Nav />
      <main className={isLanding ? 'main main-wide' : 'main'}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/farmer" element={<RequireAuth><FarmerPage /></RequireAuth>} />
          <Route path="/young" element={<YoungPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
        </Routes>
      </main>
    </>
  )
}

function Root() {
  return (
    <BrowserRouter>
      <App />
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Root />
  </React.StrictMode>
)
