import { useState, useRef } from 'react'
import { api, type FarmDetail, type MatchItem, type SupportProgramItem } from '../api'

const CROP_NAMES: Record<string, string> = { APPLE: '사과', PEACH: '복숭아', GRAPE: '포도' }
const SUCC_NAMES: Record<string, string> = { SALE: '매도', LEASE: '임대', JOINT: '공동경영', MENTORING: '멘토후독립' }

const SIDO_LIST = ['충북', '경북', '충남']

interface ScoreBarProps { label: string; value: number; max: number }
function ScoreBar({ label, value, max }: ScoreBarProps) {
  return (
    <div className="score-bar">
      <span className="score-bar-label">{label}</span>
      <div className="score-bar-track">
        <div className="score-bar-fill" style={{ width: `${(value / max) * 100}%` }} />
      </div>
      <span className="score-bar-val">{value.toFixed(1)}</span>
    </div>
  )
}

function MatchCard({ item, rank, yfId }: { item: MatchItem; rank: number; yfId: number }) {
  const fmt = (n: number) => n.toLocaleString('ko-KR')
  const score = Math.round(item.total_score)
  const circleColor = score >= 70 ? 'var(--green)' : score >= 40 ? '#f59e0b' : '#9ca3af'

  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<FarmDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [message, setMessage] = useState('')
  const [contactName, setContactName] = useState('')
  const [contactPhone, setContactPhone] = useState('')
  const [consultState, setConsultState] = useState<'idle' | 'sending' | 'sent' | 'error'>('idle')

  const toggle = async () => {
    const next = !expanded
    setExpanded(next)
    if (next && detail === null) {
      setDetailLoading(true)
      try {
        const d = await api.getFarmDetail(item.farm_id)
        setDetail(d)
      } catch {
        // 상세 조회 실패해도 카드 자체는 펼쳐진 상태 유지 (PDF·상담신청은 그대로 가능)
      } finally {
        setDetailLoading(false)
      }
    }
  }

  const submitConsult = async (e: React.FormEvent) => {
    e.preventDefault()
    setConsultState('sending')
    try {
      await api.createConsultRequest(item.farm_id, {
        young_farmer_id: yfId,
        message: message || null,
        contact_name: contactName || null,
        contact_phone: contactPhone || null,
      })
      setConsultState('sent')
    } catch {
      setConsultState('error')
    }
  }

  return (
    <div className="match-item clickable" onClick={toggle}>
      <div className="match-header">
        <div className="match-info">
          <div className="match-farm-name">
            <span style={{ color: 'var(--gray)', marginRight: '.3rem' }}>#{rank}</span>
            {CROP_NAMES[item.crop_code] || item.crop_code} 농장 ({item.sido})
          </div>
          <div className="match-farm-meta">
            {item.address}
          </div>
          <div className="match-farm-meta" style={{ marginTop: '.25rem' }}>
            <span className="tag">{CROP_NAMES[item.crop_code]}</span>
            <span className="tag">{item.tree_age ? `${item.tree_age}년생` : '-'}</span>
            <span className="tag">{(item.area_m2 / 10000).toFixed(2)}ha</span>
            {item.succession_type && <span className="tag">{SUCC_NAMES[item.succession_type]}</span>}
          </div>
          <div className="value-range-small">
            인수 검토가: {fmt(item.est_value_min)} ~ {fmt(item.est_value_max)}만원
          </div>
          {item.risk_penalty > 0 && (
            <span className="penalty-badge">리스크 -{item.risk_penalty}점</span>
          )}
        </div>
        <div className="match-score-circle" style={{ background: circleColor }}>
          <span className="match-score-num">{score}</span>
          <span className="match-score-unit">/ 100</span>
        </div>
      </div>

      <div className="score-bars">
        <ScoreBar label="지역" value={item.region_score} max={20} />
        <ScoreBar label="작목" value={item.crop_score} max={20} />
        <ScoreBar label="자본" value={item.capital_score} max={20} />
        <ScoreBar label="경험" value={item.experience_score} max={15} />
        <ScoreBar label="승계" value={item.succession_score} max={15} />
        <ScoreBar label="정책금" value={item.policy_score} max={10} />
      </div>

      {item.explanation && (
        <p style={{ fontSize: '.8rem', color: 'var(--gray)', margin: '.6rem 0 0', fontStyle: 'italic' }}>
          “{item.explanation}”
        </p>
      )}

      {expanded && (
        <div className="match-detail" onClick={e => e.stopPropagation()}>
          {detailLoading && <div className="match-farm-meta">상세 정보 불러오는 중...</div>}

          {detail && detail.assets.length > 0 && (
            <div className="match-detail-assets">
              <div className="card-title" style={{ fontSize: '.85rem', marginBottom: '.4rem' }}>시설 현황</div>
              {detail.assets.map((a, i) => (
                <div key={i} className="match-farm-meta">
                  {a.facility_name} · {a.area_m2.toLocaleString('ko-KR')}㎡
                  {a.installed_year ? ` · ${a.installed_year}년 설치` : ''} · {a.condition_grade}등급
                </div>
              ))}
            </div>
          )}

          <a
            href={api.reportPdfUrl(item.farm_id)}
            className="btn btn-primary"
            style={{ display: 'block', textAlign: 'center', marginTop: '.8rem', textDecoration: 'none' }}
            target="_blank"
            rel="noopener noreferrer"
          >
            PDF 리포트 다운로드
          </a>

          {consultState === 'sent' ? (
            <div className="consult-success">상담 신청이 접수되었습니다.</div>
          ) : (
            <form className="consult-form" onSubmit={submitConsult}>
              <input
                type="text"
                required
                placeholder="이름"
                value={contactName}
                onChange={e => setContactName(e.target.value)}
                disabled={consultState === 'sending'}
                style={{ marginBottom: '.5rem' }}
              />
              <input
                type="text"
                placeholder="연락처 (선택)"
                value={contactPhone}
                onChange={e => setContactPhone(e.target.value)}
                disabled={consultState === 'sending'}
                style={{ marginBottom: '.5rem' }}
              />
              <textarea
                placeholder="농가에 전달할 메시지 (선택)"
                value={message}
                onChange={e => setMessage(e.target.value)}
                disabled={consultState === 'sending'}
              />
              {consultState === 'error' && <div className="error-box">상담 신청에 실패했습니다. 다시 시도해주세요.</div>}
              <button type="submit" className="btn btn-primary" disabled={consultState === 'sending'}>
                {consultState === 'sending' ? <span className="spinner" /> : '상담 신청'}
              </button>
            </form>
          )}
        </div>
      )}
    </div>
  )
}

function SupportProgramPanel({ programs }: { programs: SupportProgramItem[] }) {
  if (programs.length === 0) return null
  return (
    <div className="card">
      <div className="card-title">추천 지원사업</div>
      {programs.map(p => (
        <div key={p.program_code} className="match-item" style={{ cursor: 'default' }}>
          <div className="match-farm-name">{p.name}</div>
          <div className="match-farm-meta">{p.description}</div>
          <div className="value-range-small">{p.amount_text}</div>
          {p.pitch && (
            <p style={{ fontSize: '.8rem', color: 'var(--gray)', margin: '.5rem 0 0', fontStyle: 'italic' }}>
              “{p.pitch}”
            </p>
          )}
          {p.apply_url && (
            <a href={p.apply_url} target="_blank" rel="noopener noreferrer" style={{ fontSize: '.8rem', display: 'inline-block', marginTop: '.4rem' }}>
              신청 안내 보기 →
            </a>
          )}
        </div>
      ))}
    </div>
  )
}

export default function YoungPage() {
  const [form, setForm] = useState({
    pref_sido: '충북',
    pref_crop: 'APPLE',
    available_capital: '15000',
    experience_years: '3',
    policy_fund: true,
    pref_succession: 'SALE',
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [matches, setMatches] = useState<MatchItem[] | null>(null)
  const [programs, setPrograms] = useState<SupportProgramItem[]>([])
  const [yfId, setYfId] = useState<number | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const reg = await api.createYoungFarmer({
        pref_sido: form.pref_sido || null,
        pref_crop: form.pref_crop || null,
        available_capital: parseFloat(form.available_capital) * 10_000,
        experience_years: parseInt(form.experience_years) || 0,
        policy_fund: form.policy_fund,
        pref_succession: form.pref_succession,
      })
      setYfId(reg.young_farmer_id)
      const res = await api.getMatches(reg.young_farmer_id)
      setMatches(res.matches)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
      try {
        const sp = await api.getSupportPrograms(reg.young_farmer_id)
        setPrograms(sp.programs)
      } catch {
        // 지원사업 조회 실패해도 매칭 결과는 그대로 표시 (부수 정보)
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '서버 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page page-young">
      <header className="hero hero-young">
        <span className="hero-eyebrow"><span className="dot"></span>청년농 매칭</span>
        <h1>내 조건에 맞는 농장을<br />점수로 만나보세요</h1>
        <p>희망 지역·작목·자본을 입력하면 승계 가능한 농장을 매칭 점수순으로 추천해 드립니다.</p>
      </header>

      <form className="card" onSubmit={handleSubmit}>
        <div className="card-title">나의 영농 조건</div>

        {error && <div className="error-box">{error}</div>}

        <div className="form-row">
          <div className="form-group">
            <label>희망 지역</label>
            <select value={form.pref_sido} onChange={set('pref_sido')}>
              <option value="">상관없음</option>
              {SIDO_LIST.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="form-group">
            <label>희망 작목</label>
            <select value={form.pref_crop} onChange={set('pref_crop')}>
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
            <input type="number" min="0" value={form.available_capital} onChange={set('available_capital')} placeholder="예: 15000" />
          </div>
          <div className="form-group">
            <label>영농 경력 (년)</label>
            <input type="number" min="0" max="50" value={form.experience_years} onChange={set('experience_years')} />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>승계 선호</label>
            <select value={form.pref_succession} onChange={set('pref_succession')}>
              <option value="SALE">매도</option>
              <option value="LEASE">임대</option>
              <option value="JOINT">공동경영</option>
              <option value="MENTORING">멘토후독립</option>
            </select>
          </div>
          <div className="form-group" style={{ display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
            <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', cursor: 'pointer', marginBottom: 0 }}>
              <input
                type="checkbox"
                style={{ width: 'auto' }}
                checked={form.policy_fund}
                onChange={set('policy_fund')}
              />
              청년창업농 정책자금 신청 예정
            </label>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : '매칭 농장 찾기'}
        </button>
      </form>

      {matches !== null && (
        <div ref={resultRef}>
          <p className="section-title">
            매칭 결과 {matches.length}개
            {yfId && <span style={{ fontSize: '.8rem', color: 'var(--gray)', fontWeight: 400, marginLeft: '.5rem' }}>ID #{yfId}</span>}
          </p>

          {matches.length === 0 ? (
            <div className="empty">
              <div style={{ fontSize: '2rem', marginBottom: '.5rem' }}>🌾</div>
              조건에 맞는 농장이 없습니다.
            </div>
          ) : (
            matches.map((m, i) => <MatchCard key={m.farm_id} item={m} rank={i + 1} yfId={yfId!} />)
          )}

          {matches.length > 0 && (
            <div className="disclaimer" style={{ marginTop: '.5rem' }}>
              {matches[0].disclaimer}
            </div>
          )}

          <SupportProgramPanel programs={programs} />
        </div>
      )}
    </div>
  )
}
