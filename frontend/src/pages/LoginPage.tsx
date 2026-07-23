import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { api, setToken, setRole } from '../api'

type Role = 'FARMER' | 'YOUNG'

const SIDO_LIST = ['충북', '경북', '충남']

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [role, setRoleState] = useState<Role>('FARMER')
  const [form, setForm] = useState({ email: '', password: '', name: '', phone: '' })
  const [prof, setProf] = useState({
    pref_sido: '충북', pref_crop: 'APPLE', capital_manwon: '15000',
    experience_years: '3', policy_fund: true, pref_succession: 'SALE', intro: '',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))
  const setP = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setProf(p => ({ ...p, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))

  // RequireAuth가 튕겨보낸 원래 목적지 — 있으면 로그인 후 그리로 복귀
  // (예: 랜딩 진단 카드 → /farmer → 로그인 → 다시 /farmer, 주소 프리필 유지)
  const nextPath = (useLocation().state as { next?: string } | null)?.next
  const routeByRole = (r: string) =>
    navigate(nextPath ?? (r === 'YOUNG' ? '/young' : '/dashboard'))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      if (mode === 'login') {
        const result = await api.login({ email: form.email, password: form.password })
        setToken(result.token); setRole(result.role); routeByRole(result.role)
      } else {
        const result = await api.register({ email: form.email, password: form.password, name: form.name, phone: form.phone || undefined, role })
        setToken(result.token); setRole(result.role)
        // 청년농 가입 시 프로필도 함께 생성
        if (role === 'YOUNG') {
          await api.putMyProfile({
            pref_sido: prof.pref_sido || null,
            pref_crop: prof.pref_crop || null,
            available_capital: (parseFloat(prof.capital_manwon) || 0) * 10000,
            experience_years: parseInt(prof.experience_years) || 0,
            policy_fund: prof.policy_fund,
            pref_succession: prof.pref_succession,
            intro: prof.intro || null,
          })
        }
        routeByRole(result.role)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '서버 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page-wrap" style={{ maxWidth: 480 }}>
      <p className="section-title">{mode === 'login' ? '로그인' : '회원가입'}</p>

      <form className="card" onSubmit={handleSubmit}>
        {error && <div className="error-box">{error}</div>}

        {mode === 'register' && (
          <div className="form-group">
            <label>가입 유형</label>
            <div className="role-toggle">
              <button
                type="button"
                className={role === 'FARMER' ? 'active' : ''}
                onClick={() => setRoleState('FARMER')}
              >
                농장주
                <span>농장을 등록·승계</span>
              </button>
              <button
                type="button"
                className={role === 'YOUNG' ? 'active' : ''}
                onClick={() => setRoleState('YOUNG')}
              >
                청년농
                <span>농장을 찾아 인수</span>
              </button>
            </div>
          </div>
        )}

        {mode === 'register' && (
          <div className="form-group">
            <label>이름</label>
            <input type="text" required value={form.name} onChange={set('name')} placeholder="홍길동" />
          </div>
        )}

        <div className="form-group">
          <label>이메일</label>
          <input type="email" required value={form.email} onChange={set('email')} placeholder="you@example.com" />
        </div>

        <div className="form-group">
          <label>비밀번호</label>
          <input type="password" required minLength={8} value={form.password} onChange={set('password')} placeholder="8자 이상" />
        </div>

        {mode === 'register' && (
          <div className="form-group">
            <label>연락처 (선택)</label>
            <input type="text" value={form.phone} onChange={set('phone')} placeholder="010-0000-0000" />
          </div>
        )}

        {mode === 'register' && role === 'YOUNG' && (
          <>
            <div className="role-divider">청년농 프로필 (농장주에게 보여집니다)</div>
            <div className="form-row">
              <div className="form-group">
                <label>관심 지역</label>
                <select value={prof.pref_sido} onChange={setP('pref_sido')}>
                  <option value="">상관없음</option>
                  {SIDO_LIST.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>
              <div className="form-group">
                <label>관심 작목</label>
                <select value={prof.pref_crop} onChange={setP('pref_crop')}>
                  <option value="">상관없음</option>
                  <option value="APPLE">사과</option>
                  <option value="PEACH">복숭아</option>
                  <option value="GRAPE">포도</option>
                </select>
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>보유 자본 (만원)</label>
                <input type="number" min="0" value={prof.capital_manwon} onChange={setP('capital_manwon')} placeholder="예: 15000" />
              </div>
              <div className="form-group">
                <label>영농 경력 (년)</label>
                <input type="number" min="0" max="50" value={prof.experience_years} onChange={setP('experience_years')} />
              </div>
            </div>
            <div className="form-group">
              <label>희망 승계 방식</label>
              <select value={prof.pref_succession} onChange={setP('pref_succession')}>
                <option value="SALE">매도</option>
                <option value="LEASE">임대</option>
                <option value="JOINT">공동경영</option>
                <option value="MENTORING">멘토후독립</option>
              </select>
            </div>
            <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', cursor: 'pointer', marginBottom: '.8rem' }}>
              <input type="checkbox" style={{ width: 'auto' }} checked={prof.policy_fund} onChange={setP('policy_fund')} />
              청년창업농 정책자금 신청 예정
            </label>
          </>
        )}

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : (mode === 'login' ? '로그인' : '가입하기')}
        </button>

        <p style={{ textAlign: 'center', fontSize: '.85rem', marginTop: '.8rem' }}>
          {mode === 'login' ? (
            <>계정이 없으신가요?{' '}
              <a href="#" onClick={e => { e.preventDefault(); setMode('register'); setError(null) }}>회원가입</a>
            </>
          ) : (
            <>이미 계정이 있으신가요?{' '}
              <a href="#" onClick={e => { e.preventDefault(); setMode('login'); setError(null) }}>로그인</a>
            </>
          )}
        </p>
      </form>
    </div>
  )
}
