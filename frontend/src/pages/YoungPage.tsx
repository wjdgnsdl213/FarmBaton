import { useState, useRef, useEffect } from 'react'
import { createPortal } from 'react-dom'
import { Link } from 'react-router-dom'
import { api, getToken, getRole, type FarmDetail, type MatchItem, type SupportProgramItem } from '../api'
import { formatArea, formatManwonRange } from '../format'
import heroYoung from '../assets/hero-young.jpg'

interface Account { name: string; phone: string | null }

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

function MatchCard({ item, rank, yfId, account }: { item: MatchItem; rank: number; yfId: number | null; account: Account | null }) {
  const score = Math.round(item.total_score)
  const circleColor = score >= 70 ? 'var(--green)' : score >= 40 ? '#f59e0b' : '#9ca3af'

  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<FarmDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const [programs, setPrograms] = useState<SupportProgramItem[] | null>(null)
  const [message, setMessage] = useState('')
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
    if (next && programs === null && yfId) {
      try {
        const sp = await api.getSupportPrograms(yfId, item.farm_id)
        setPrograms(sp.programs)
      } catch {
        setPrograms([])
      }
    }
  }

  const submitConsult = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!yfId) return
    setConsultState('sending')
    try {
      await api.createConsultRequest(item.farm_id, {
        young_farmer_id: yfId,
        message: message || null,
      })
      setConsultState('sent')
    } catch {
      setConsultState('error')
    }
  }

  return (
    <div className="match-item clickable" style={{ borderLeftColor: circleColor }} onClick={toggle}>
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
            <span className="tag">{formatArea(item.area_m2)}</span>
            {item.succession_type && <span className="tag">{SUCC_NAMES[item.succession_type]}</span>}
          </div>
          <div className="value-range-small">
            인수 검토가: {formatManwonRange(item.est_value_min, item.est_value_max)}
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

      {expanded && createPortal(
        <div className="modal-backdrop" onClick={() => setExpanded(false)}>
          <div className="modal-panel" onClick={e => e.stopPropagation()}>
            <button type="button" className="modal-close" aria-label="닫기" onClick={() => setExpanded(false)}>×</button>
            <div className="match-farm-name">
              #{rank} {CROP_NAMES[item.crop_code] || item.crop_code} 농장 ({item.sido})
            </div>
            <div className="match-farm-meta">{item.address}</div>
            <div className="value-range-small" style={{ marginBottom: '1rem' }}>
              인수 검토가: {formatManwonRange(item.est_value_min, item.est_value_max)}
            </div>

            {detailLoading && <div className="match-farm-meta">상세 정보 불러오는 중...</div>}

            {detail && detail.assets.length > 0 && (
              <div className="match-detail-assets">
                <div className="match-detail-section-title">시설 현황</div>
                <div className="detail-list">
                  {detail.assets.map((a, i) => (
                    <div key={i} className="detail-row">
                      <div className="detail-row-title">{a.facility_name}</div>
                      <div className="detail-row-meta">
                        {a.area_m2.toLocaleString('ko-KR')}㎡
                        {a.installed_year ? ` · ${a.installed_year}년 설치` : ' · 설치연도 미상'} · {a.condition_grade}등급
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {programs && programs.length > 0 && (
              <div className="match-detail-assets">
                <div className="match-detail-section-title">이 농장에 맞는 지원사업</div>
                <div className="detail-list">
                  {programs.map(p => (
                    <div key={p.program_code} className="detail-row">
                      <div className="detail-row-title">{p.name}</div>
                      <div className="detail-row-meta">{p.amount_text}</div>
                      {p.pitch && <div className="detail-row-pitch">“{p.pitch}”</div>}
                      {p.apply_url && (
                        <a href={p.apply_url} target="_blank" rel="noopener noreferrer" className="detail-row-link">
                          신청 안내 보기 →
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <a
              href={api.reportPdfUrl(item.farm_id, 'young')}
              className="btn btn-primary"
              style={{ display: 'block', textAlign: 'center', marginTop: '.8rem', textDecoration: 'none' }}
              target="_blank"
              rel="noopener noreferrer"
            >
              PDF 리포트 다운로드
            </a>

            {consultState === 'sent' ? (
              <div className="consult-success">상담 신청이 접수되었습니다. 농장주가 수락하면 채팅으로 이어집니다.</div>
            ) : !account ? (
              <div className="consult-login-prompt">
                <p>상담 신청은 청년농 로그인 후 가능합니다.</p>
                <Link to="/login" className="btn btn-primary">로그인하고 신청하기</Link>
              </div>
            ) : !yfId ? (
              <div className="consult-login-prompt">
                <p>상담 신청 전에 내 프로필(자본·경력 등)을 먼저 작성해주세요.</p>
                <Link to="/profile" className="btn btn-primary">내 정보에서 프로필 작성</Link>
              </div>
            ) : (
              <form className="consult-form" onSubmit={submitConsult}>
                <div className="consult-account">
                  <div className="detail-row-title">{account.name} 님 계정으로 신청</div>
                  <div className="detail-row-meta">검색 조건이 아니라 내 정보에 설정한 프로필이 농장주에게 전달됩니다.</div>
                </div>
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
        </div>,
        document.body
      )}
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
  const [otherCropMatches, setOtherCropMatches] = useState<MatchItem[]>([])
  const [showOtherCrops, setShowOtherCrops] = useState(false)
  const [resultCrop, setResultCrop] = useState<string | null>(null)
  const [yfId, setYfId] = useState<number | null>(null)
  const [account, setAccount] = useState<Account | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  // 로그인 청년농: 계정(상담용 이름) + 실제 프로필(검색 폼 기본값)을 불러온다.
  useEffect(() => {
    if (!getToken() || getRole() !== 'YOUNG') return
    api.getMe()
      .then(me => setAccount({ name: me.name, phone: me.phone ?? null }))
      .catch(() => setAccount(null))
    api.getMyProfile()
      .then(p => {
        if (p.young_farmer_id) setYfId(p.young_farmer_id)
        setForm(f => ({
          ...f,
          pref_sido: p.pref_sido ?? f.pref_sido,
          pref_crop: p.pref_crop ?? f.pref_crop,
          available_capital: p.available_capital ? String(Math.round(p.available_capital / 10000)) : f.available_capital,
          experience_years: String(p.experience_years ?? f.experience_years),
          policy_fund: p.policy_fund,
          pref_succession: p.pref_succession ?? f.pref_succession,
        }))
      })
      .catch(() => {})
  }, [])

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.type === 'checkbox' ? (e.target as HTMLInputElement).checked : e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      // 검색은 미저장 — 입력값은 탐색에만 쓰이고 내 프로필을 바꾸지 않는다.
      const res = await api.matchSearch({
        pref_sido: form.pref_sido || null,
        pref_crop: form.pref_crop || null,
        available_capital: parseFloat(form.available_capital) * 10_000,
        experience_years: parseInt(form.experience_years) || 0,
        policy_fund: form.policy_fund,
        pref_succession: form.pref_succession,
      })
      setYfId(res.young_farmer_id || null)   // 본인 실제 프로필 id (상담용)
      setMatches(res.matches)
      setOtherCropMatches(res.other_crop_matches ?? [])
      setShowOtherCrops(false)
      setResultCrop(form.pref_crop || null)
      setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
    } catch (err: any) {
      setError(err.response?.data?.detail || '서버 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="page page-young">
      <header className="hero hero-young">
        <img src={heroYoung} alt="" className="hero-photo" />
        <div className="hero-overlay" />
        <div className="hero-inner">
          <span className="hero-eyebrow">청년농 매칭</span>
          <h1>내 조건에 맞는 농장을<br />점수로 만나보세요</h1>
          <p>희망 지역·작목·자본을 입력하면 승계 가능한 농장을 매칭하고, 점수순으로 추천해 드립니다.</p>
        </div>
      </header>

      <div className="page-wrap-wide">
      <form className="card" onSubmit={handleSubmit}>
        <div className="card-title">농장 검색 조건</div>
        <p className="match-farm-meta" style={{ margin: '-.4rem 0 1rem' }}>
          검색 조건은 저장되지 않습니다. 상담 신청 시 농장주에게는 <strong>내 정보</strong>에 설정한 프로필이 전달됩니다.
        </p>

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
            <label style={{ display: 'flex', alignItems: 'center', gap: '.5rem', cursor: 'pointer', marginBottom: '.3rem' }}>
              <input
                type="checkbox"
                style={{ width: 'auto' }}
                checked={form.policy_fund}
                onChange={set('policy_fund')}
              />
              청년창업농 정책자금 신청 예정
            </label>
            <p style={{ fontSize: '.76rem', color: 'var(--gray)', lineHeight: 1.5, margin: 0 }}>
              체크하면 정책자금 융자 한도(5억원) 안에서 인수 가능한 농장을 매칭 점수에서 우대합니다.
            </p>
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : '매칭 농장 찾기'}
        </button>
      </form>

      {matches !== null && (
        <div className="scroll-anchor" ref={resultRef}>
          <p className="section-title">
            {resultCrop
              ? `희망 작목 · ${CROP_NAMES[resultCrop]} 농장 ${matches.length}개`
              : `매칭 결과 ${matches.length}개`}
            {yfId && <span style={{ fontSize: '.8rem', color: 'var(--gray)', fontWeight: 400, marginLeft: '.5rem' }}>ID #{yfId}</span>}
          </p>

          {matches.length === 0 ? (
            <div className="empty">
              {resultCrop
                ? `현재 등록된 ${CROP_NAMES[resultCrop]} 농장이 없습니다.`
                : '조건에 맞는 농장이 없습니다.'}
            </div>
          ) : (
            <div className="match-grid">
              {matches.map((m, i) => <MatchCard key={m.farm_id} item={m} rank={i + 1} yfId={yfId} account={account} />)}
            </div>
          )}

          {resultCrop && otherCropMatches.length > 0 && (
            <div className="other-crop-section">
              <button
                type="button"
                className="other-crop-toggle"
                aria-expanded={showOtherCrops}
                onClick={() => setShowOtherCrops(open => !open)}
              >
                <span>
                  추천할 만한 다른 작목 농장 보기
                  <small>{otherCropMatches.length}개</small>
                </span>
                <span aria-hidden="true">{showOtherCrops ? '접기 ↑' : '보기 ↓'}</span>
              </button>
              {showOtherCrops && (
                <div className="other-crop-results">
                  <p>
                    희망 작목과는 다르지만 지역·자본·승계 조건의 매칭 점수가 높은 농장입니다.
                  </p>
                  <div className="match-grid">
                    {otherCropMatches.map((m, i) => (
                      <MatchCard
                        key={m.farm_id}
                        item={m}
                        rank={i + 1}
                        yfId={yfId}
                        account={account}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {(matches.length > 0 || otherCropMatches.length > 0) && (
            <div className="disclaimer" style={{ marginTop: '.5rem' }}>
              {(matches[0] ?? otherCropMatches[0]).disclaimer}
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  )
}
