import React, { useState, useEffect } from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage'
import FarmerPage from './pages/FarmerPage'
import YoungPage from './pages/YoungPage'
import LoginPage from './pages/LoginPage'
import DashboardPage from './pages/DashboardPage'
import MyRequestsPage from './pages/MyRequestsPage'
import ConversationsPage from './pages/ConversationsPage'
import ProfilePage from './pages/ProfilePage'
import { getToken, getRole, clearToken } from './api'
import logoImg from './assets/logo.png'
import './style.css'

function RoleNotice({ requiredRole }: { requiredRole: 'FARMER' | 'YOUNG' }) {
  const roleLabel = requiredRole === 'FARMER' ? '농장주' : '청년농'
  const myRole = getRole()
  const backTo = myRole === 'YOUNG' ? '/young' : '/dashboard'
  const backLabel = myRole === 'YOUNG' ? '청년농 매칭으로 가기' : '내 농장으로 가기'
  return (
    <div className="role-notice">
      <div className="role-notice-card">
        <div className="role-notice-icon" aria-hidden="true">🔒</div>
        <h2>{roleLabel} 전용 메뉴입니다</h2>
        <p>
          이 페이지는 {roleLabel} 계정만 이용할 수 있습니다.
          {myRole === 'YOUNG' && requiredRole === 'FARMER'
            ? ' 청년농 계정은 농장을 찾아 인수하는 쪽이라 농가 등록은 제공되지 않습니다.'
            : ''}
        </p>
        <Link className="btn btn-primary" to={backTo}>{backLabel}</Link>
      </div>
    </div>
  )
}

function RequireAuth({ children, role }: { children: React.ReactNode; role?: 'FARMER' | 'YOUNG' }) {
  if (!getToken()) return <Navigate to="/login" replace />
  // 역할이 지정된 라우트인데 다른 역할로 로그인했으면 전용 메뉴 안내 표시
  if (role && getRole() && getRole() !== role) {
    return <RoleNotice requiredRole={role} />
  }
  return <>{children}</>
}

function NavLinks({ loc, activeSection, loggedIn, role, onLogout, onNavigate }: {
  loc: ReturnType<typeof useLocation>
  activeSection: string | null
  loggedIn: boolean
  role: string | null
  onLogout: () => void
  onNavigate?: () => void
}) {
  const isActive = (path: string) => loc.pathname === path ? 'active' : ''
  const isSection = (id: string) => loc.pathname === '/' && activeSection === id ? 'active' : ''
  return (
    <>
      <Link className={`lp-nav-scroll ${isSection('features')}`} to="/#features" onClick={onNavigate}>서비스 소개</Link>
      <Link className={`lp-nav-scroll ${isSection('steps')}`} to="/#steps" onClick={onNavigate}>작동 방식</Link>
      <span className="lp-nav-divider" aria-hidden="true" />
      <Link className={`lp-nav-page ${isActive('/farmer')}`} to="/farmer" onClick={onNavigate}>농가 등록</Link>
      <Link className={`lp-nav-page ${isActive('/young')}`} to="/young" onClick={onNavigate}>청년농 매칭</Link>
      <span className="lp-nav-divider" aria-hidden="true" />
      {loggedIn ? (
        <>
          {role !== 'YOUNG' && (
            <Link className={isActive('/dashboard')} to="/dashboard" onClick={onNavigate}>내 농장</Link>
          )}
          {role === 'YOUNG' && (
            <Link className={isActive('/my-requests')} to="/my-requests" onClick={onNavigate}>내 상담</Link>
          )}
          <Link className={isActive('/conversations')} to="/conversations" onClick={onNavigate}>대화</Link>
          <Link className={isActive('/profile')} to="/profile" onClick={onNavigate}>내 정보</Link>
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
  const role = getRole()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [activeSection, setActiveSection] = useState<string | null>(null)

  // 랜딩 페이지에서 스크롤 위치에 따라 현재 보고 있는 섹션을 메뉴에 표시 (스크롤스파이)
  useEffect(() => {
    if (loc.pathname !== '/') { setActiveSection(null); return }
    const ids = ['features', 'steps']
    const visible = new Set<string>()
    let obs: IntersectionObserver | null = null
    let raf = 0
    const setup = () => {
      const els = ids.map(id => document.getElementById(id)).filter(Boolean) as HTMLElement[]
      if (els.length === 0) { raf = requestAnimationFrame(setup); return }
      obs = new IntersectionObserver(entries => {
        entries.forEach(e => { e.isIntersecting ? visible.add(e.target.id) : visible.delete(e.target.id) })
        setActiveSection(ids.find(id => visible.has(id)) ?? null)
      }, { rootMargin: '-45% 0px -50% 0px', threshold: 0 })
      els.forEach(el => obs!.observe(el))
    }
    setup()
    return () => { cancelAnimationFrame(raf); obs?.disconnect() }
  }, [loc.pathname])

  const logout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <nav className="lp-nav">
      <div className="lp-wrap lp-nav-inner">
        <Link className="lp-logo" to="/" onClick={() => setMobileOpen(false)}>
          <img src={logoImg} className="lp-logo-img" alt="팜바톤" />
        </Link>
        <div className="lp-nav-links">
          <NavLinks loc={loc} activeSection={activeSection} loggedIn={loggedIn} role={role} onLogout={logout} />
        </div>
        <div className="lp-nav-right">
          {!loggedIn && <Link className="lp-pill lp-pill-warm" to="/farmer">시작하기 →</Link>}
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
          <NavLinks loc={loc} activeSection={activeSection} loggedIn={loggedIn} role={role} onLogout={logout} onNavigate={() => setMobileOpen(false)} />
        </div>
      )}
    </nav>
  )
}

function App() {
  const loc = useLocation()
  const isWide = loc.pathname === '/' || loc.pathname === '/farmer' || loc.pathname === '/young' || loc.pathname === '/conversations'

  return (
    <>
      <Nav />
      <main className={isWide ? 'main main-wide' : 'main'}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/farmer" element={<RequireAuth role="FARMER"><FarmerPage /></RequireAuth>} />
          <Route path="/young" element={<RequireAuth role="YOUNG"><YoungPage /></RequireAuth>} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<RequireAuth role="FARMER"><DashboardPage /></RequireAuth>} />
          <Route path="/my-requests" element={<RequireAuth role="YOUNG"><MyRequestsPage /></RequireAuth>} />
          <Route path="/conversations" element={<RequireAuth><ConversationsPage /></RequireAuth>} />
          <Route path="/profile" element={<RequireAuth><ProfilePage /></RequireAuth>} />
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
