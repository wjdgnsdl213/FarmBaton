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
  const loc = useLocation()
  // 로그인 후 원래 가려던 페이지로 복귀할 수 있게 목적지를 넘긴다
  if (!getToken()) return <Navigate to="/login" replace state={{ next: loc.pathname }} />
  // 역할이 지정된 라우트인데 다른 역할로 로그인했으면 전용 메뉴 안내 표시.
  // ADMIN은 농가·청년농 양쪽 라우트를 모두 통과한다(운영/시연용).
  if (role && getRole() && getRole() !== role && getRole() !== 'ADMIN') {
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
          <Link className={isActive('/conversations')} to="/conversations" onClick={onNavigate}>채팅</Link>
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
  // 메뉴 클릭 시 scrollIntoView('start')로 섹션이 상단에 붙으므로, 감지 기준도
  // nav 바로 아래(line)를 통과한 마지막 섹션으로 잡아 도착 위치와 일치시킨다.
  useEffect(() => {
    if (loc.pathname !== '/') { setActiveSection(null); return }
    const ids = ['features', 'steps']
    const line = 80 // nav 높이(64px) + 여유
    let ticking = false
    const compute = () => {
      ticking = false
      let current: string | null = null
      for (const id of ids) {
        const el = document.getElementById(id)
        if (el && el.getBoundingClientRect().top <= line) current = id
      }
      setActiveSection(current)
    }
    const onScroll = () => { if (!ticking) { ticking = true; requestAnimationFrame(compute) } }
    compute()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [loc.pathname])

  const logout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <nav className="lp-nav">
      <div className="lp-wrap lp-nav-inner">
        <Link className="lp-logo" to="/" onClick={() => setMobileOpen(false)}>
          <img src={logoImg} className="lp-logo-img" alt="" />
          <span className="lp-logo-word">팜바톤</span>
        </Link>
        <div className="lp-nav-links">
          <NavLinks loc={loc} activeSection={activeSection} loggedIn={loggedIn} role={role} onLogout={logout} />
        </div>
        <div className="lp-nav-right">
          {!loggedIn && <Link className="lp-pill lp-pill-warm" to="/">시작하기 →</Link>}
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
