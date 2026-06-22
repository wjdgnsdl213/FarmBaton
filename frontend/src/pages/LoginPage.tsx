import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, setToken } from '../api'

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [form, setForm] = useState({ email: '', password: '', name: '', phone: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const result = mode === 'login'
        ? await api.login({ email: form.email, password: form.password })
        : await api.register({ email: form.email, password: form.password, name: form.name, phone: form.phone || undefined })
      setToken(result.token)
      navigate('/dashboard')
    } catch (err: any) {
      setError(err.response?.data?.detail || '서버 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <p className="section-title">농가 {mode === 'login' ? '로그인' : '회원가입'}</p>

      <form className="card" onSubmit={handleSubmit}>
        {error && <div className="error-box">{error}</div>}

        {mode === 'register' && (
          <div className="form-group">
            <label>이름</label>
            <input type="text" required value={form.name} onChange={set('name')} placeholder="홍길동" />
          </div>
        )}

        <div className="form-group">
          <label>이메일</label>
          <input type="email" required value={form.email} onChange={set('email')} placeholder="farmer@example.com" />
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
