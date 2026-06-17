import { useState, useRef } from 'react'
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import { api, type ValuationResult } from '../api'

// Leaflet 기본 마커 아이콘 경로 수정 (Vite 번들러 이슈)
delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const CROP_NAMES: Record<string, string> = { APPLE: '사과', PEACH: '복숭아', GRAPE: '포도' }
const SUCC_NAMES: Record<string, string> = { SALE: '매도', LEASE: '임대', JOINT: '공동경영', MENTORING: '멘토후독립' }
const GRADE_DESC: Record<string, string> = {
  A: '실사 기반 추정', B: '농가 제출자료 기반', C: '사전 검토용 추정', D: '참고용 자동 추정'
}

function MapPicker({ position, onChange }: { position: [number, number] | null; onChange: (p: [number, number]) => void }) {
  useMapEvents({ click: e => onChange([e.latlng.lat, e.latlng.lng]) })
  return position ? <Marker position={position} /> : null
}

export default function FarmerPage() {
  const [form, setForm] = useState({
    address: '', crop_code: 'APPLE', tree_age: '10',
    succession_type: 'SALE', area_m2: '',
  })
  const [mapPos, setMapPos] = useState<[number, number] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ValuationResult | null>(null)
  const resultRef = useRef<HTMLDivElement>(null)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.address.trim()) { setError('주소를 입력하세요.'); return }
    setError(null)
    setLoading(true)
    try {
      const payload: any = {
        address: form.address,
        crop_code: form.crop_code,
        tree_age: parseInt(form.tree_age) || 0,
        succession_type: form.succession_type,
      }
      if (mapPos) { payload.lat = mapPos[0]; payload.lon = mapPos[1] }
      if (form.area_m2) payload.area_m2 = parseFloat(form.area_m2)

      const res = await api.createFarm(payload)
      if (res.valuation) {
        setResult(res.valuation)
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
      } else {
        setError(res.warning || '가치평가를 산출하지 못했습니다.')
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || '서버 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const fmt = (n: number) => n.toLocaleString('ko-KR')

  return (
    <div>
      <p className="section-title">농가 등록 &amp; 인수 검토 리포트</p>

      <div className="card">
        <div className="card-title">농장 위치를 지도에서 선택하세요 (선택)</div>
        <div className="map-wrap">
          <MapContainer
            center={[36.5, 127.8]}
            zoom={7}
            style={{ height: '220px', width: '100%' }}
            scrollWheelZoom={false}
          >
            <TileLayer
              url="https://api.vworld.kr/req/wmts/1.0.0/40635DD8-06B0-30B5-ACA9-E406704465E8/Base/{z}/{y}/{x}.png"
              attribution="V-World"
              errorTileUrl="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
            />
            <MapPicker position={mapPos} onChange={setMapPos} />
          </MapContainer>
        </div>
        {mapPos && (
          <p style={{ fontSize: '.78rem', color: 'var(--gray)' }}>
            선택 좌표: {mapPos[0].toFixed(5)}, {mapPos[1].toFixed(5)}
          </p>
        )}
      </div>

      <form className="card" onSubmit={handleSubmit}>
        <div className="card-title">농장 정보 입력</div>

        {error && <div className="error-box">{error}</div>}

        <div className="form-group">
          <label>주소 *</label>
          <input value={form.address} onChange={set('address')} placeholder="예: 충청북도 충주시 가주동 483" />
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>작목 *</label>
            <select value={form.crop_code} onChange={set('crop_code')}>
              <option value="APPLE">사과</option>
              <option value="PEACH">복숭아</option>
              <option value="GRAPE">포도</option>
            </select>
          </div>
          <div className="form-group">
            <label>주요 수령 (년)</label>
            <input type="number" min="0" max="99" value={form.tree_age} onChange={set('tree_age')} />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>승계 방식</label>
            <select value={form.succession_type} onChange={set('succession_type')}>
              <option value="SALE">매도</option>
              <option value="LEASE">임대</option>
              <option value="JOINT">공동경영</option>
              <option value="MENTORING">멘토후독립</option>
            </select>
          </div>
          <div className="form-group">
            <label>면적 ㎡ (지도 선택 없을 때)</label>
            <input type="number" min="0" value={form.area_m2} onChange={set('area_m2')} placeholder="예: 3000" />
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : '인수 검토 리포트 산출'}
        </button>
      </form>

      {result && (
        <div className="card" ref={resultRef}>
          <div className="card-title">
            인수 검토가 범위(참고용 추정)&nbsp;
            <span className="grade-badge">등급 {result.confidence_grade} — {GRADE_DESC[result.confidence_grade]}</span>
          </div>

          <div className="valuation-header">
            <div className="valuation-range">
              {fmt(result.est_value_min)}만원 ~ {fmt(result.est_value_max)}만원
            </div>
            <div className="valuation-sublabel">{result.label}</div>
          </div>

          <div className="valuation-grid">
            <div className="val-item">
              <div className="val-item-label">예상 연소득</div>
              <div className="val-item-value">{fmt(result.est_income_min)} ~ {fmt(result.est_income_max)}만원</div>
            </div>
            <div className="val-item">
              <div className="val-item-label">토지 기준가</div>
              <div className="val-item-value">{fmt(result.land_value_point)}만원</div>
            </div>
            <div className="val-item">
              <div className="val-item-label">시설 잔존가</div>
              <div className="val-item-value">{fmt(result.facility_value)}만원</div>
            </div>
            <div className="val-item">
              <div className="val-item-label">영업권</div>
              <div className="val-item-value">
                {result.goodwill_min === 0 ? '해당 없음' : `${fmt(result.goodwill_min)} ~ ${fmt(result.goodwill_max)}만원`}
              </div>
            </div>
          </div>

          <div className="disclaimer">{result.disclaimer}</div>
        </div>
      )}
    </div>
  )
}
