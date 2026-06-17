import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom'
import FarmerPage from './pages/FarmerPage'
import YoungPage from './pages/YoungPage'
import './style.css'

function Nav() {
  const loc = useLocation()
  return (
    <nav className="nav">
      <span className="nav-logo">🌾 팜바톤</span>
      <div className="nav-links">
        <Link className={`nav-link ${loc.pathname === '/' ? 'active' : ''}`} to="/">농가 등록</Link>
        <Link className={`nav-link ${loc.pathname === '/young' ? 'active' : ''}`} to="/young">청년농 매칭</Link>
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
          <Route path="/" element={<FarmerPage />} />
          <Route path="/young" element={<YoungPage />} />
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
