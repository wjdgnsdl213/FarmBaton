import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type MyConsultRequest } from '../api'

const STATUS_NAMES: Record<string, string> = { REQUESTED: '대기중', ACCEPTED: '수락됨', DECLINED: '거절됨' }

export default function MyRequestsPage() {
  const [requests, setRequests] = useState<MyConsultRequest[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fmt = (n: number | null) => n === null ? '-' : n.toLocaleString('ko-KR')

  useEffect(() => {
    api.getMyConsultRequests()
      .then(setRequests)
      .catch(err => setError(err.response?.data?.detail || '상담 목록을 불러오지 못했습니다.'))
  }, [])

  return (
    <div className="page-wrap">
      <p className="section-title">내 상담</p>
      {error && <div className="error-box">{error}</div>}
      {requests === null ? (
        <div className="match-farm-meta">불러오는 중...</div>
      ) : requests.length === 0 ? (
        <div className="empty">
          아직 신청한 상담이 없습니다.<br />
          <Link to="/young" style={{ display: 'inline-block', marginTop: '.6rem' }}>농장 매칭 보러 가기 →</Link>
        </div>
      ) : (
        requests.map(r => (
          <div key={r.id} className="card">
            <div className="card-title" style={{ marginBottom: '.5rem' }}>{r.farm_label}</div>
            <div className="match-farm-meta">{r.address}</div>
            <div className="value-range-small">
              인수 검토가: {fmt(r.est_value_min)} ~ {fmt(r.est_value_max)}만원 ·{' '}
              <span className="tag">{STATUS_NAMES[r.status] || r.status}</span>
            </div>

            {r.status === 'ACCEPTED' ? (
              <div className="consult-success" style={{ marginTop: '.6rem' }}>
                수락됨 — <Link to="/conversations">대화 메뉴</Link>에서 대화하세요.
              </div>
            ) : r.status === 'REQUESTED' ? (
              <div className="match-farm-meta" style={{ marginTop: '.5rem' }}>농장주의 수락을 기다리고 있습니다.</div>
            ) : (
              <div className="match-farm-meta" style={{ marginTop: '.5rem' }}>농장주가 거절한 신청입니다.</div>
            )}
          </div>
        ))
      )}
    </div>
  )
}
