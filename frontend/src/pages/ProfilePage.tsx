import { useEffect, useState } from 'react'
import { api, getRole, type MeResult, type YoungProfile } from '../api'

const ROLE_NAMES: Record<string, string> = { FARMER: '농장주', YOUNG: '청년농', ADMIN: '관리자' }
const SIDO_LIST = ['충북', '경북', '충남']

function AccountSection() {
  const [me, setMe] = useState<MeResult | null>(null)
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getMe().then(m => { setMe(m); setName(m.name); setPhone(m.phone ?? '') }).catch(() => {})
  }, [])

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true); setSaved(false); setError(null)
    try {
      const m = await api.updateMe({ name, phone: phone || null })
      setMe(m); setSaved(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || '저장에 실패했습니다.')
    } finally {
      setSaving(false)
    }
  }

  if (!me) return <div className="card"><div className="match-farm-meta">불러오는 중...</div></div>

  return (
    <form className="card" onSubmit={save}>
      <div className="card-title">계정 정보</div>
      {error && <div className="error-box">{error}</div>}
      <div className="form-row">
        <div className="form-group">
          <label>이메일 (변경 불가)</label>
          <input type="text" value={me.email} disabled />
        </div>
        <div className="form-group">
          <label>구분</label>
          <input type="text" value={ROLE_NAMES[me.role] || me.role} disabled />
        </div>
      </div>
      <div className="form-group">
        <label>이름</label>
        <input type="text" required value={name} onChange={e => { setName(e.target.value); setSaved(false) }} />
      </div>
      <div className="form-group">
        <label>연락처</label>
        <input type="text" value={phone} onChange={e => { setPhone(e.target.value); setSaved(false) }} placeholder="010-0000-0000" />
      </div>
      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? <span className="spinner" /> : '저장'}
      </button>
      {saved && <div className="consult-success" style={{ marginTop: '.6rem' }}>저장되었습니다.</div>}
    </form>
  )
}

function PasswordSection() {
  const [cur, setCur] = useState('')
  const [next, setNext] = useState('')
  const [state, setState] = useState<'idle' | 'saving' | 'done' | 'error'>('idle')
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setState('saving'); setError(null)
    try {
      await api.changePassword(cur, next)
      setState('done'); setCur(''); setNext('')
    } catch (err: any) {
      setError(err.response?.data?.detail || '변경에 실패했습니다.')
      setState('error')
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      <div className="card-title">비밀번호 변경</div>
      {error && <div className="error-box">{error}</div>}
      <div className="form-group">
        <label>현재 비밀번호</label>
        <input type="password" required value={cur} onChange={e => setCur(e.target.value)} />
      </div>
      <div className="form-group">
        <label>새 비밀번호 (8자 이상)</label>
        <input type="password" required minLength={8} value={next} onChange={e => setNext(e.target.value)} />
      </div>
      <button type="submit" className="btn btn-primary" disabled={state === 'saving'}>
        {state === 'saving' ? <span className="spinner" /> : '비밀번호 변경'}
      </button>
      {state === 'done' && <div className="consult-success" style={{ marginTop: '.6rem' }}>비밀번호가 변경되었습니다.</div>}
    </form>
  )
}

function YoungProfileSection() {
  const [p, setP] = useState<YoungProfile | null>(null)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getMyProfile().then(setP).catch(() => setError('프로필을 불러오지 못했습니다.'))
  }, [])

  const upd = (patch: Partial<YoungProfile>) => { setP(prev => prev ? { ...prev, ...patch } : prev); setSaved(false) }

  const save = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!p) return
    setSaving(true); setSaved(false); setError(null)
    try {
      const next = await api.putMyProfile({
        pref_sido: p.pref_sido || null,
        pref_crop: p.pref_crop || null,
        available_capital: p.available_capital,
        experience_years: p.experience_years,
        policy_fund: p.policy_fund,
        pref_succession: p.pref_succession,
        intro: p.intro || null,
      })
      setP(next); setSaved(true)
    } catch (err: any) {
      setError(err.response?.data?.detail || '저장에 실패했습니다.')
    } finally {
      setSaving(false)
    }
  }

  if (!p) return <div className="card"><div className="match-farm-meta">청년농 프로필 불러오는 중...</div></div>

  const capManwon = p.available_capital ? String(Math.round(p.available_capital / 10000)) : ''

  return (
    <form className="card" onSubmit={save}>
      <div className="card-title">청년농 프로필</div>
      <p className="match-farm-meta" style={{ margin: '-.4rem 0 1rem' }}>
        농장에 상담을 신청하면 이 프로필이 농장주에게 전달됩니다. (검색 조건과 별개)
      </p>
      {error && <div className="error-box">{error}</div>}
      <div className="form-row">
        <div className="form-group">
          <label>관심 지역</label>
          <select value={p.pref_sido || ''} onChange={e => upd({ pref_sido: e.target.value || null })}>
            <option value="">상관없음</option>
            {SIDO_LIST.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
        <div className="form-group">
          <label>관심 작목</label>
          <select value={p.pref_crop || ''} onChange={e => upd({ pref_crop: e.target.value || null })}>
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
          <input type="number" min="0" value={capManwon}
            onChange={e => upd({ available_capital: (parseFloat(e.target.value) || 0) * 10000 })} placeholder="예: 15000" />
        </div>
        <div className="form-group">
          <label>영농 경력 (년)</label>
          <input type="number" min="0" max="50" value={p.experience_years}
            onChange={e => upd({ experience_years: parseInt(e.target.value) || 0 })} />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>희망 승계 방식</label>
          <select value={p.pref_succession} onChange={e => upd({ pref_succession: e.target.value })}>
            <option value="SALE">매도</option>
            <option value="LEASE">임대</option>
            <option value="JOINT">공동경영</option>
            <option value="MENTORING">멘토후독립</option>
          </select>
        </div>
        <div className="form-group" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', cursor: 'pointer', marginBottom: '.45rem' }}>
            <input type="checkbox" style={{ width: 'auto' }} checked={p.policy_fund}
              onChange={e => upd({ policy_fund: e.target.checked })} />
            청년창업농 정책자금 신청 예정
          </label>
        </div>
      </div>
      <div className="form-group">
        <label>한 줄 자기소개 (선택)</label>
        <textarea value={p.intro || ''} onChange={e => upd({ intro: e.target.value })}
          placeholder="영농 계획, 강점 등 농장주에게 보여줄 한 줄 소개" />
      </div>
      <button type="submit" className="btn btn-primary" disabled={saving}>
        {saving ? <span className="spinner" /> : '프로필 저장'}
      </button>
      {saved && <div className="consult-success" style={{ marginTop: '.6rem' }}>저장되었습니다.</div>}
    </form>
  )
}

export default function ProfilePage() {
  const isYoung = getRole() === 'YOUNG'
  return (
    <div className="page-wrap" style={{ maxWidth: 560 }}>
      <p className="section-title">내 정보</p>
      <AccountSection />
      {isYoung && <YoungProfileSection />}
      <PasswordSection />
    </div>
  )
}
