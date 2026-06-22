import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
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

function Nav() {
  const loc = useLocation()
  const navigate = useNavigate()
  const loggedIn = !!getToken()

  const logout = () => {
    clearToken()
    navigate('/login')
  }

  return (
    <nav className="nav">
      <span className="nav-logo">🌾 팜바톤</span>
      <div className="nav-links">
        <Link className={`nav-link ${loc.pathname === '/' ? 'active' : ''}`} to="/">농가 등록</Link>
        <Link className={`nav-link ${loc.pathname === '/young' ? 'active' : ''}`} to="/young">청년농 매칭</Link>
        {loggedIn ? (
          <>
            <Link className={`nav-link ${loc.pathname === '/dashboard' ? 'active' : ''}`} to="/dashboard">내 농장</Link>
            <a className="nav-link" href="#" onClick={e => { e.preventDefault(); logout() }}>로그아웃</a>
          </>
        ) : (
          <Link className={`nav-link ${loc.pathname === '/login' ? 'active' : ''}`} to="/login">로그인</Link>
        )}
      </div>
    </nav>
  )
}

function App() {
  return (
    <BrowserRouter>
      <Nav />
      <main className="main">
        <Routes>
          <Route path="/" element={<RequireAuth><FarmerPage /></RequireAuth>} />
          <Route path="/young" element={<YoungPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/dashboard" element={<RequireAuth><DashboardPage /></RequireAuth>} />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
