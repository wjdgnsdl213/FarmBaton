import { useEffect, useState } from 'react'
import { api, type ConsultRequestDetail, type FarmMatchItem, type FarmSummary } from '../api'
import ChatPanel from '../components/ChatPanel'

const CROP_NAMES: Record<string, string> = { APPLE: '사과', PEACH: '복숭아', GRAPE: '포도' }
const SUCC_NAMES: Record<string, string> = { SALE: '매도', LEASE: '임대', JOINT: '공동경영', MENTORING: '멘토후독립' }
const STATUS_NAMES: Record<string, string> = { REQUESTED: '대기중', ACCEPTED: '수락', DECLINED: '거절' }
const FARM_STATUS_NAMES: Record<string, string> = { DRAFT: '비공개', ACTIVE: '공개중', MATCHED: '매칭완료', CLOSED: '종료' }

function ScoreBar({ label, value, max }: { label: string; value: number; max: number }) {
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

function MatchedYoungFarmers({ farmId }: { farmId: number }) {
  const [matches, setMatches] = useState<FarmMatchItem[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getFarmMatches(farmId)
      .then(res => setMatches(res.matches))
      .catch(err => setError(err.response?.data?.detail || '매칭 목록을 불러오지 못했습니다.'))
  }, [farmId])

  if (error) return <div className="error-box">{error}</div>
  if (matches === null) return <div className="match-farm-meta">매칭 목록 불러오는 중...</div>
  if (matches.length === 0) {
    return <div className="match-farm-meta">아직 매칭되는 청년농이 없습니다. (공개 상태이며 가치평가가 있어야 매칭됩니다)</div>
  }

  return (
    <div>
      {matches.map(m => {
        const score = Math.round(m.total_score)
        const circleColor = score >= 70 ? 'var(--green)' : score >= 40 ? '#f59e0b' : '#9ca3af'
        return (
          <div key={m.young_farmer_id} className="match-item" style={{ cursor: 'default', borderLeftColor: circleColor }}>
            <div className="match-header">
              <div className="match-info">
                <div className="match-farm-name">청년농 #{m.young_farmer_id}</div>
                <div className="match-farm-meta" style={{ marginTop: '.25rem' }}>
                  <span className="tag">{m.pref_sido || '지역 무관'}</span>
                  <span className="tag">{m.pref_crop ? CROP_NAMES[m.pref_crop] : '작목 무관'}</span>
                  <span className="tag">{SUCC_NAMES[m.pref_succession]}</span>
                  <span className="tag">자본 {m.available_capital.toLocaleString('ko-KR')}만원</span>
                  <span className="tag">경력 {m.experience_years}년</span>
                </div>
              </div>
              <div className="match-score-circle" style={{ background: circleColor }}>
                <span className="match-score-num">{score}</span>
                <span className="match-score-unit">/ 100</span>
              </div>
            </div>
            <div className="score-bars">
              <ScoreBar label="지역" value={m.region_score} max={20} />
              <ScoreBar label="작목" value={m.crop_score} max={20} />
              <ScoreBar label="자본" value={m.capital_score} max={20} />
              <ScoreBar label="경험" value={m.experience_score} max={15} />
              <ScoreBar label="승계" value={m.succession_score} max={15} />
              <ScoreBar label="정책금" value={m.policy_score} max={10} />
            </div>
            {m.explanation && (
              <p style={{ fontSize: '.8rem', color: 'var(--gray)', margin: '.6rem 0 0', fontStyle: 'italic' }}>
                "{m.explanation}"
              </p>
            )}
          </div>
        )
      })}
    </div>
  )
}

function ConsultInbox({ farmId, onFarmStatusChange }: { farmId: number; onFarmStatusChange: (status: string) => void }) {
  const [requests, setRequests] = useState<ConsultRequestDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [chatOpen, setChatOpen] = useState<number | null>(null)

  useEffect(() => {
    api.getConsultRequests(farmId)
      .then(setRequests)
      .catch(err => setError(err.response?.data?.detail || '상담 신청 목록을 불러오지 못했습니다.'))
  }, [farmId])

  const updateStatus = async (reqId: number, status: 'ACCEPTED' | 'DECLINED') => {
    const updated = await api.updateConsultRequestStatus(farmId, reqId, status)
    setRequests(reqs => reqs && reqs.map(r => r.id === reqId ? { ...r, status: updated.status } : r))
    if (updated.farm_status) onFarmStatusChange(updated.farm_status)
  }

  if (error) return <div className="error-box">{error}</div>
  if (requests === null) return <div className="match-farm-meta">상담 신청 불러오는 중...</div>
  if (requests.length === 0) return <div className="match-farm-meta">아직 들어온 상담 신청이 없습니다.</div>

  return (
    <div>
      {requests.map(r => {
        const score = Math.round(r.total_score)
        const circleColor = score >= 70 ? 'var(--green)' : score >= 40 ? '#f59e0b' : '#9ca3af'
        return (
          <div key={r.id} className="match-item" style={{ cursor: 'default', borderLeftColor: circleColor }}>
            <div className="match-header">
              <div className="match-info">
                <div className="match-farm-name">{r.applicant_name || '청년농'}</div>
                <div className="match-farm-meta" style={{ marginTop: '.25rem' }}>
                  <span className="tag">{r.pref_sido || '지역 무관'}</span>
                  <span className="tag">{r.pref_crop ? CROP_NAMES[r.pref_crop] : '작목 무관'}</span>
                  <span className="tag">{SUCC_NAMES[r.pref_succession]}</span>
                  <span className="tag">자본 {r.available_capital.toLocaleString('ko-KR')}만원</span>
                  <span className="tag">경력 {r.experience_years}년</span>
                </div>
                {r.message && <p style={{ fontSize: '.85rem', margin: '.5rem 0 0' }}>"{r.message}"</p>}
                <div className="match-farm-meta" style={{ marginTop: '.4rem' }}>
                  <span className="tag">{STATUS_NAMES[r.status] || r.status}</span>
                  <span style={{ marginLeft: '.4rem' }}>{new Date(r.created_at).toLocaleString('ko-KR')}</span>
                </div>
              </div>
              <div className="match-score-circle" style={{ background: circleColor }}>
                <span className="match-score-num">{score}</span>
                <span className="match-score-unit">/ 100</span>
              </div>
            </div>
            {r.status === 'REQUESTED' && (
              <div style={{ display: 'flex', gap: '.5rem', marginTop: '.6rem' }}>
                <button className="btn btn-primary" onClick={() => updateStatus(r.id, 'ACCEPTED')}>수락</button>
                <button className="btn" style={{ background: 'var(--gray-light)', color: 'var(--text)' }} onClick={() => updateStatus(r.id, 'DECLINED')}>거절</button>
              </div>
            )}
            {r.status === 'ACCEPTED' && (
              <div style={{ marginTop: '.6rem' }}>
                <button
                  className="btn btn-primary"
                  onClick={() => setChatOpen(o => o === r.id ? null : r.id)}
                >
                  {chatOpen === r.id ? '채팅 닫기' : '채팅 열기'}
                </button>
                {chatOpen === r.id && (
                  <div style={{ marginTop: '.6rem' }}>
                    <ChatPanel reqId={r.id} title={`${r.applicant_name || '청년농'} 님과의 대화`} />
                  </div>
                )}
              </div>
            )}
            {r.status === 'DECLINED' && (
              <div className="match-farm-meta" style={{ marginTop: '.5rem' }}>거절한 신청입니다.</div>
            )}
          </div>
        )
      })}
    </div>
  )
}

function FarmCard({ farm }: { farm: FarmSummary }) {
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState(farm.status)
  const [publishing, setPublishing] = useState(false)
  const fmt = (n: number | null) => n === null ? '-' : n.toLocaleString('ko-KR')

  const toggleStatus = async () => {
    const next = status === 'ACTIVE' ? 'DRAFT' : 'ACTIVE'
    setPublishing(true)
    try {
      const res = await api.updateFarmStatus(farm.id, next)
      setStatus(res.status)
    } catch {
      // 실패 시 상태 유지, 버튼으로 재시도 가능
    } finally {
      setPublishing(false)
    }
  }

  return (
    <div className="card">
      <div className="card-title">
        {CROP_NAMES[farm.crop_code] || farm.crop_code} 농장 ({farm.sido}) · {(farm.area_m2 / 10000).toFixed(2)}ha
      </div>
      <div className="match-farm-meta">{farm.address}</div>
      <div className="value-range-small">
        인수 검토가: {fmt(farm.est_value_min)} ~ {fmt(farm.est_value_max)}만원 · <span className="tag">{FARM_STATUS_NAMES[status] || status}</span>
      </div>

      {(status === 'ACTIVE' || status === 'DRAFT') && (
        <button
          className="btn"
          style={{ marginTop: '.6rem', background: 'var(--gray-light)', color: 'var(--text)' }}
          onClick={toggleStatus}
          disabled={publishing}
        >
          {publishing ? <span className="spinner" /> : status === 'ACTIVE' ? '매칭 풀에서 비공개로 전환' : '매칭 풀에 공개하기'}
        </button>
      )}

      <button className="btn btn-primary" style={{ marginTop: '.6rem' }} onClick={() => setOpen(o => !o)}>
        {open ? '청년농 관리 접기' : '청년농 관리'}
      </button>

      {open && (
        <div style={{ marginTop: '.8rem', paddingTop: '.8rem', borderTop: '1px solid var(--border)' }}>
          <p className="section-title" style={{ margin: '0 0 .6rem' }}>상담 신청</p>
          <ConsultInbox farmId={farm.id} onFarmStatusChange={setStatus} />

          <p className="section-title" style={{ margin: '1.2rem 0 .6rem' }}>매칭 후보 (미신청)</p>
          <p className="match-farm-meta" style={{ marginBottom: '.6rem' }}>
            아직 신청하지 않았지만 이 농장과 조건이 맞는 청년농입니다. 점수 미리보기용이며 직접 연락은 상담 신청에서 가능합니다.
          </p>
          <MatchedYoungFarmers farmId={farm.id} />
        </div>
      )}
    </div>
  )
}

export default function DashboardPage() {
  const [farms, setFarms] = useState<FarmSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getMyFarms()
      .then(setFarms)
      .catch(err => setError(err.response?.data?.detail || '농장 목록을 불러오지 못했습니다.'))
  }, [])

  return (
    <div>
      <p className="section-title">내 농장</p>
      {error && <div className="error-box">{error}</div>}
      {farms === null ? (
        <div className="match-farm-meta">불러오는 중...</div>
      ) : farms.length === 0 ? (
        <div className="empty">
          <div style={{ fontSize: '2rem', marginBottom: '.5rem' }}>🌾</div>
          등록한 농장이 없습니다.
        </div>
      ) : (
        farms.map(f => <FarmCard key={f.id} farm={f} />)
      )}
    </div>
  )
}
