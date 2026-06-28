import { useState, useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Marker, useMap } from 'react-leaflet'
import L from 'leaflet'
import { api, type ValuationResult } from '../api'
import heroFarmer from '../assets/hero-farmer.jpg'

delete (L.Icon.Default.prototype as any)._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const GRADE_DESC: Record<string, string> = {
  A: '실사 기반 추정', B: '농가 제출자료 기반', C: '사전 검토용 추정', D: '참고용 자동 추정',
}

// 지오코딩 결과로 지도 이동
function MapFlyTo({ position }: { position: [number, number] | null }) {
  const map = useMap()
  useEffect(() => {
    if (position) map.flyTo(position, 16, { duration: 1 })
  }, [position, map])
  return null
}

export default function FarmerPage() {
  const [form, setForm] = useState({
    address: '', crop_code: 'APPLE', tree_age: '10',
    succession_type: 'SALE', area_m2: '',
  })
  const [mapPos, setMapPos] = useState<[number, number] | null>(null)
  const [geocoding, setGeocoding] = useState(false)
  const [geocodeError, setGeocodeError] = useState<string | null>(null)
  const [parcelInfo, setParcelInfo] = useState<{ area_m2?: number; sigungu?: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ValuationResult | null>(null)
  const [publishState, setPublishState] = useState<'idle' | 'publishing' | 'published' | 'error'>('idle')
  const resultRef = useRef<HTMLDivElement>(null)

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleGeocode = async () => {
    if (!form.address.trim()) return
    setGeocoding(true)
    setGeocodeError(null)
    setParcelInfo(null)
    try {
      const res = await api.geocode(form.address, form.crop_code)
      setMapPos([res.lat, res.lon])
      // 면적 자동 취득
      if (res.area_m2) {
        setForm(f => ({ ...f, area_m2: String(Math.round(res.area_m2!)) }))
        setParcelInfo({ area_m2: res.area_m2, sigungu: res.sigungu })
      }
    } catch {
      setGeocodeError('주소를 찾을 수 없습니다. 지번 또는 도로명 주소로 다시 입력해보세요.')
    } finally {
      setGeocoding(false)
    }
  }

  const handleAddressKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') { e.preventDefault(); handleGeocode() }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.address.trim()) { setError('주소를 입력하세요.'); return }
    if (!mapPos && !form.area_m2) {
      setError('주소 검색으로 위치를 확인하거나, 면적을 직접 입력하세요.')
      return
    }
    setError(null)
    setLoading(true)
    try {
      const payload = {
        address: form.address,
        crop_code: form.crop_code,
        tree_age: parseInt(form.tree_age) || 0,
        succession_type: form.succession_type,
        lat: mapPos?.[0],
        lon: mapPos?.[1],
        area_m2: form.area_m2 ? parseFloat(form.area_m2) : undefined,
      }

      const res = await api.createFarm(payload)
      if (res.valuation) {
        setResult(res.valuation)
        setPublishState('idle')
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: 'smooth' }), 100)
      } else {
        setError(res.warning || '가치평가를 산출하지 못했습니다.')
      }
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: string } } }
      setError(e.response?.data?.detail || '서버 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  const handlePublish = async () => {
    if (!result) return
    setPublishState('publishing')
    try {
      await api.updateFarmStatus(result.farm_id, 'ACTIVE')
      setPublishState('published')
    } catch {
      setPublishState('error')
    }
  }

  const fmt = (n: number) => n.toLocaleString('ko-KR')

  return (
    <div className="page page-farmer">
      <header className="hero hero-farmer">
        <img src={heroFarmer} alt="" className="hero-photo" />
        <div className="hero-overlay" />
        <div className="hero-inner">
          <span className="hero-eyebrow">농가 승계 진단</span>
          <h1>내 농장의 인수 검토가<br />범위로 정리됩니다</h1>
          <p>주소와 작목만 입력하면 예상 소득·토지·시설 가치를 한눈에 확인할 수 있습니다.</p>
        </div>
      </header>

      <div className="page-wrap">
      <form className="card" onSubmit={handleSubmit}>
        <div className="card-title">농장 정보 입력</div>

        {error && <div className="error-box">{error}</div>}

        {/* 주소 + 검색 버튼 */}
        <div className="form-group">
          <label>주소 *</label>
          <div style={{ display: 'flex', gap: '.5rem' }}>
            <input
              value={form.address}
              onChange={set('address')}
              onKeyDown={handleAddressKeyDown}
              placeholder="예: 충청북도 충주시 가주동 483"
              style={{ flex: 1 }}
            />
            <button
              type="button"
              className="btn btn-primary"
              style={{ width: 'auto', padding: '.6rem 1rem', whiteSpace: 'nowrap' }}
              onClick={handleGeocode}
              disabled={geocoding || !form.address.trim()}
            >
              {geocoding ? <span className="spinner" /> : '위치 검색'}
            </button>
          </div>
          {geocodeError && (
            <p style={{ fontSize: '.78rem', color: '#b91c1c', marginTop: '.3rem' }}>{geocodeError}</p>
          )}
          {mapPos && !geocodeError && (
            <p style={{ fontSize: '.78rem', color: 'var(--green)', marginTop: '.3rem' }}>
              위치 확인됨
              {parcelInfo?.sigungu ? ` — ${parcelInfo.sigungu}` : ''}
              {parcelInfo?.area_m2
                ? ` · 필지 면적 ${parcelInfo.area_m2.toLocaleString('ko-KR')}㎡ 자동 적용`
                : ' — 면적을 직접 입력해주세요'}
            </p>
          )}
        </div>

        {/* 지도 (위치 확인용) */}
        <div className="map-wrap">
          <MapContainer
            center={[36.5, 127.8]}
            zoom={7}
            style={{ height: '200px', width: '100%' }}
            scrollWheelZoom={false}
          >
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution="OpenStreetMap"
            />
            <MapFlyTo position={mapPos} />
            {mapPos && <Marker position={mapPos} />}
          </MapContainer>
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
            <label>
              면적 ㎡
              {parcelInfo?.area_m2
                ? <span style={{ color: 'var(--green)', fontWeight: 400 }}> (자동 취득)</span>
                : <span style={{ color: 'var(--gray)', fontWeight: 400 }}> (검색 후 자동 입력)</span>}
            </label>
            <input
              type="number" min="0" value={form.area_m2}
              onChange={set('area_m2')} placeholder="위치 검색 시 자동 입력"
            />
          </div>
        </div>

        <button type="submit" className="btn btn-primary" disabled={loading}>
          {loading ? <span className="spinner" /> : '인수 검토 리포트 산출'}
        </button>
      </form>

      {result && (
        <div className="card scroll-anchor" ref={resultRef}>
          <div className="card-title">
            인수 검토가 범위(참고용 추정)&nbsp;
            <span className="grade-badge">
              {result.confidence_grade}등급 — {GRADE_DESC[result.confidence_grade]}
            </span>
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
              <div className="val-item-value">
                {fmt(result.est_income_min)} ~ {fmt(result.est_income_max)}만원
              </div>
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
                {result.goodwill_min === 0
                  ? '해당 없음'
                  : `${fmt(result.goodwill_min)} ~ ${fmt(result.goodwill_max)}만원`}
              </div>
            </div>
          </div>

          <div className="disclaimer">{result.disclaimer}</div>

          {publishState === 'published' ? (
            <div className="consult-success" style={{ marginTop: '.8rem' }}>
              ✓ 매칭 풀에 공개되었습니다 — 이제 청년농 매칭 리스트에 노출됩니다.
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              style={{ marginTop: '.8rem' }}
              onClick={handlePublish}
              disabled={publishState === 'publishing'}
            >
              {publishState === 'publishing' ? <span className="spinner" /> : '매칭 풀에 공개하기'}
            </button>
          )}
          {publishState === 'error' && (
            <div className="error-box" style={{ marginTop: '.5rem' }}>공개 처리에 실패했습니다. 다시 시도해주세요.</div>
          )}
          <p style={{ fontSize: '.78rem', color: 'var(--gray)', margin: '.4rem 0 0' }}>
            공개하지 않아도 등록은 완료되며, 리포트는 아래에서 언제든 다시 받을 수 있습니다.
          </p>

          <a
            href={api.reportPdfUrl(result.farm_id, 'farmer')}
            className="btn btn-primary"
            style={{ display: 'block', textAlign: 'center', marginTop: '.6rem', textDecoration: 'none' }}
            target="_blank"
            rel="noopener noreferrer"
          >
            PDF 리포트 다운로드
          </a>
        </div>
      )}
      </div>
    </div>
  )
}
