import { useEffect, useState } from 'react'
import { api, type ConsultRequestDetail, type FarmSummary } from '../api'

const CROP_NAMES: Record<string, string> = { APPLE: '사과', PEACH: '복숭아', GRAPE: '포도' }
const STATUS_NAMES: Record<string, string> = { REQUESTED: '대기중', ACCEPTED: '수락', DECLINED: '거절' }

function ConsultInbox({ farmId }: { farmId: number }) {
  const [requests, setRequests] = useState<ConsultRequestDetail[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.getConsultRequests(farmId)
      .then(setRequests)
      .catch(err => setError(err.response?.data?.detail || '상담 신청 목록을 불러오지 못했습니다.'))
  }, [farmId])

  const updateStatus = async (reqId: number, status: 'ACCEPTED' | 'DECLINED') => {
    const updated = await api.updateConsultRequestStatus(farmId, reqId, status)
    setRequests(reqs => reqs && reqs.map(r => r.id === reqId ? { ...r, status: updated.status } : r))
  }

  if (error) return <div className="error-box">{error}</div>
  if (requests === null) return <div className="match-farm-meta">상담 신청 불러오는 중...</div>
  if (requests.length === 0) return <div className="match-farm-meta">아직 들어온 상담 신청이 없습니다.</div>

  return (
    <div>
      {requests.map(r => (
        <div key={r.id} className="match-item" style={{ cursor: 'default' }}>
          <div className="match-farm-name">{r.contact_name || '익명'}</div>
          <div className="match-farm-meta">{r.contact_phone || '연락처 미입력'}</div>
          {r.message && <p style={{ fontSize: '.85rem', margin: '.4rem 0' }}>"{r.message}"</p>}
          <div className="match-farm-meta" style={{ marginTop: '.3rem' }}>
            <span className="tag">{STATUS_NAMES[r.status] || r.status}</span>
            <span style={{ marginLeft: '.4rem' }}>{new Date(r.created_at).toLocaleString('ko-KR')}</span>
          </div>
          {r.status === 'REQUESTED' && (
            <div style={{ display: 'flex', gap: '.5rem', marginTop: '.6rem' }}>
              <button className="btn btn-primary" onClick={() => updateStatus(r.id, 'ACCEPTED')}>수락</button>
              <button className="btn" style={{ background: 'var(--gray-light)', color: 'var(--text)' }} onClick={() => updateStatus(r.id, 'DECLINED')}>거절</button>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}

function FarmCard({ farm }: { farm: FarmSummary }) {
  const [expanded, setExpanded] = useState(false)
  const fmt = (n: number | null) => n === null ? '-' : n.toLocaleString('ko-KR')

  return (
    <div className="card">
      <div className="card-title" style={{ cursor: 'pointer' }} onClick={() => setExpanded(e => !e)}>
        {CROP_NAMES[farm.crop_code] || farm.crop_code} 농장 ({farm.sido}) · {(farm.area_m2 / 10000).toFixed(2)}ha
      </div>
      <div className="match-farm-meta">{farm.address}</div>
      <div className="value-range-small">
        인수 검토가: {fmt(farm.est_value_min)} ~ {fmt(farm.est_value_max)}만원 · <span className="tag">{farm.status}</span>
      </div>
      <button className="btn btn-primary" style={{ marginTop: '.8rem' }} onClick={() => setExpanded(e => !e)}>
        {expanded ? '상담 신청 접기' : '상담 신청 보기'}
      </button>
      {expanded && (
        <div style={{ marginTop: '.8rem', paddingTop: '.8rem', borderTop: '1px solid var(--border)' }}>
          <ConsultInbox farmId={farm.id} />
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
