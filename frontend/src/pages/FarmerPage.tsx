import { useState, useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Marker, GeoJSON, useMap } from 'react-leaflet'
import L from 'leaflet'
import { api, type ValuationResult, type FacilityOption } from '../api'
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

// V-World 항공영상 배경 — 키 미설정 시 OSM으로 자동 폴백(데모가 죽지 않도록)
const VWORLD_KEY = import.meta.env.VITE_VWORLD_API_KEY as string | undefined
const AERIAL_TILE_URL = VWORLD_KEY
  ? `https://api.vworld.kr/req/wmts/1.0.0/${VWORLD_KEY}/Satellite/{z}/{y}/{x}.jpeg`
  : 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
const AERIAL_ATTRIBUTION = VWORLD_KEY ? '&copy; VWorld' : 'OpenStreetMap'

const BOUNDARY_STYLE: L.PathOptions = { color: '#e11d2c', weight: 3, fillColor: '#e11d2c', fillOpacity: 0.08 }

// 지오코딩 결과로 지도 이동 — 필지 경계가 있으면 경계 전체가 보이게, 없으면 좌표로 확대
function MapFlyTo({ position, boundary }: { position: [number, number] | null; boundary?: GeoJSON.Geometry }) {
  const map = useMap()
  useEffect(() => {
    if (boundary) {
      const bounds = L.geoJSON(boundary).getBounds()
      if (bounds.isValid()) { map.flyToBounds(bounds, { padding: [24, 24], duration: 1 }); return }
    }
    if (position) map.flyTo(position, 16, { duration: 1 })
  }, [position, boundary, map])
  return null
}

export default function FarmerPage() {
  const [form, setForm] = useState({
    address: '', crop_code: 'APPLE', tree_age: '10',
    succession_type: 'SALE', area_m2: '',
  })
  const [mapPos, setMapPos] = useState<[number, number] | null>(null)
  const [boundary, setBoundary] = useState<GeoJSON.Geometry | null>(null)
  const [geocoding, setGeocoding] = useState(false)
  const [geocodeError, setGeocodeError] = useState<string | null>(null)
  const [geocodeWarning, setGeocodeWarning] = useState<string | null>(null)
  const [parcelInfo, setParcelInfo] = useState<{ area_m2?: number; sigungu?: string } | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<ValuationResult | null>(null)
  const [publishState, setPublishState] = useState<'idle' | 'publishing' | 'published' | 'error'>('idle')
  const resultRef = useRef<HTMLDivElement>(null)

  // 선택 입력: 시설·판로·매출 (영업권·시설 잔존가 정밀화 → 신뢰등급 상승)
  type AssetRow = { facility_code: string; area_m2: string; installed_year: string; condition_grade: string }
  const [showOptional, setShowOptional] = useState(false)
  const [facilityOptions, setFacilityOptions] = useState<FacilityOption[]>([])
  const [assets, setAssets] = useState<AssetRow[]>([])
  const [annualRevenue, setAnnualRevenue] = useState('')   // 만원 단위 입력
  const [salesChannel, setSalesChannel] = useState('')     // '' | 계약재배 | 직거래 | 공판장

  // 시설 종류 목록은 DB(facility_std) 기준 — 폼 진입 시 1회 로드
  useEffect(() => {
    api.facilities().then(setFacilityOptions).catch(() => setFacilityOptions([]))
  }, [])

  // 랜딩 진단 카드에서 입력한 주소 자동 입력 + 위치 검색 (LandingPage와 공유 키)
  useEffect(() => {
    const prefill = sessionStorage.getItem('fb_prefill_address')
    if (!prefill) return
    sessionStorage.removeItem('fb_prefill_address')
    setForm(f => ({ ...f, address: prefill }))
    handleGeocode(prefill)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const addAsset = () =>
    setAssets(a => [...a, { facility_code: '', area_m2: '', installed_year: '', condition_grade: 'B' }])
  const removeAsset = (i: number) => setAssets(a => a.filter((_, idx) => idx !== i))
  const updateAsset = (i: number, k: keyof AssetRow, v: string) =>
    setAssets(a => a.map((row, idx) => (idx === i ? { ...row, [k]: v } : row)))

  const set = (k: string) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [k]: e.target.value }))

  const handleGeocode = async (addressOverride?: string) => {
    const address = (addressOverride ?? form.address).trim()
    if (!address) return
    setGeocoding(true)
    setGeocodeError(null)
    setGeocodeWarning(null)
    setParcelInfo(null)
    setBoundary(null)
    try {
      const res = await api.geocode(address, form.crop_code)
      setMapPos([res.lat, res.lon])
      setBoundary(res.boundary ?? null)
      // 면적 자동 취득
      if (res.area_m2) {
        setForm(f => ({ ...f, area_m2: String(Math.round(res.area_m2!)) }))
        setParcelInfo({ area_m2: res.area_m2, sigungu: res.sigungu })
      } else if (res.warning) {
        setGeocodeWarning(res.warning)
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
      // 선택 입력: 유효한 시설 행(종류·면적 입력됨)만 전송
      const validAssets = assets
        .filter(a => a.facility_code && parseFloat(a.area_m2) > 0)
        .map(a => ({
          facility_code: a.facility_code,
          area_m2: parseFloat(a.area_m2),
          installed_year: a.installed_year ? parseInt(a.installed_year) : undefined,
          condition_grade: a.condition_grade,
        }))

      const payload = {
        address: form.address,
        crop_code: form.crop_code,
        tree_age: parseInt(form.tree_age) || 0,
        succession_type: form.succession_type,
        lat: mapPos?.[0],
        lon: mapPos?.[1],
        area_m2: form.area_m2 ? parseFloat(form.area_m2) : undefined,
        // 만원 입력 → 원 단위로 변환해 전송
        annual_revenue: annualRevenue ? Math.round(parseFloat(annualRevenue) * 10000) : undefined,
        sales_channel: salesChannel || undefined,
        assets: validAssets.length ? validAssets : undefined,
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
              onClick={() => handleGeocode()}
              disabled={geocoding || !form.address.trim()}
            >
              {geocoding ? <span className="spinner" /> : '위치 검색'}
            </button>
          </div>
          {geocodeError && (
            <p style={{ fontSize: '.78rem', color: '#b91c1c', marginTop: '.3rem' }}>{geocodeError}</p>
          )}
          {mapPos && !geocodeError && geocodeWarning && (
            <p style={{ fontSize: '.78rem', color: '#b45309', marginTop: '.3rem' }}>{geocodeWarning}</p>
          )}
          {mapPos && !geocodeError && !geocodeWarning && (
            <p style={{ fontSize: '.78rem', color: 'var(--green)', marginTop: '.3rem' }}>
              위치 확인됨
              {parcelInfo?.sigungu ? ` — ${parcelInfo.sigungu}` : ''}
              {parcelInfo?.area_m2
                ? ` · 필지 면적 ${parcelInfo.area_m2.toLocaleString('ko-KR')}㎡ 자동 적용`
                : ' — 면적을 직접 입력해주세요'}
            </p>
          )}
        </div>

        {/* 지도 (위치 확인용) — 필지 매칭 시 빨간 테두리로 경계 표시 */}
        <div className="map-wrap">
          <MapContainer
            center={[36.5, 127.8]}
            zoom={7}
            style={{ height: '260px', width: '100%' }}
            scrollWheelZoom={false}
          >
            <TileLayer url={AERIAL_TILE_URL} attribution={AERIAL_ATTRIBUTION} maxZoom={19} />
            <MapFlyTo position={mapPos} boundary={boundary ?? undefined} />
            {boundary && <GeoJSON key={JSON.stringify(boundary)} data={boundary} style={BOUNDARY_STYLE} />}
            {mapPos && !boundary && <Marker position={mapPos} />}
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

        {/* ── 선택 입력: 시설·판로·매출 (영업권·시설 잔존가 정밀화) ── */}
        <div style={{ marginTop: '.25rem' }}>
          <button
            type="button"
            onClick={() => setShowOptional(s => !s)}
            style={{
              width: '100%', display: 'flex', alignItems: 'center', gap: '.7rem',
              padding: '.85rem 1rem', borderRadius: '8px', cursor: 'pointer',
              fontFamily: 'inherit', textAlign: 'left',
              border: `1.5px ${showOptional ? 'solid' : 'dashed'} var(--green)`,
              background: showOptional ? 'var(--green-light)' : '#fff',
              transition: 'background .15s, border-color .15s',
            }}
          >
            <span style={{
              flex: '0 0 auto', width: '26px', height: '26px', borderRadius: '50%',
              display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
              background: 'var(--green)', color: '#fff', fontSize: '1.1rem',
              fontWeight: 700, lineHeight: 1,
            }}>
              {showOptional ? '−' : '+'}
            </span>
            <span style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '.1rem' }}>
              <span style={{ fontWeight: 700, fontSize: '.92rem', color: 'var(--green-deep)' }}>
                시설·판로 정보 추가 <span style={{ fontWeight: 500, color: 'var(--gray)' }}>(선택)</span>
              </span>
              <span style={{ fontSize: '.76rem', color: 'var(--gray)' }}>
                입력하면 영업권·시설 가치까지 반영돼 더 정확해져요
              </span>
            </span>
            <span style={{ flex: '0 0 auto', color: 'var(--green)', fontSize: '.8rem' }}>
              {showOptional ? '▲' : '▼'}
            </span>
          </button>

          {showOptional && (
            <div style={{
              borderLeft: '2px solid #e5e7eb', paddingLeft: '.85rem',
              marginTop: '.5rem', display: 'flex', flexDirection: 'column', gap: '.9rem',
            }}>
              {/* 시설 목록 */}
              <div>
                <label style={{ fontWeight: 600, fontSize: '.85rem' }}>보유 시설</label>
                {assets.length === 0 && (
                  <p style={{ fontSize: '.78rem', color: 'var(--gray)', margin: '.3rem 0' }}>
                    저온저장고·비닐하우스 등을 추가하면 시설 잔존가가 평가에 반영됩니다.
                  </p>
                )}
                {assets.map((a, i) => (
                  <div key={i} style={{
                    marginBottom: '.55rem', padding: '.55rem',
                    background: '#f9fafb', borderRadius: '8px',
                    display: 'flex', flexDirection: 'column', gap: '.4rem',
                  }}>
                    <select value={a.facility_code} onChange={e => updateAsset(i, 'facility_code', e.target.value)}>
                      <option value="">시설 종류 선택</option>
                      {facilityOptions.map(f => (
                        <option key={f.facility_code} value={f.facility_code}>{f.label}</option>
                      ))}
                    </select>
                    <div style={{ display: 'flex', gap: '.4rem', flexWrap: 'wrap' }}>
                      <input
                        type="number" min="0" placeholder="면적 ㎡ (예: 50)" value={a.area_m2}
                        onChange={e => updateAsset(i, 'area_m2', e.target.value)}
                        style={{ flex: '1 1 80px', minWidth: 0 }}
                      />
                      <input
                        type="number" min="1980" max="2026" placeholder="설치연도 (예: 2015)" value={a.installed_year}
                        onChange={e => updateAsset(i, 'installed_year', e.target.value)}
                        style={{ flex: '1 1 80px', minWidth: 0 }}
                      />
                      <select
                        value={a.condition_grade}
                        onChange={e => updateAsset(i, 'condition_grade', e.target.value)}
                        style={{ flex: '1 1 90px', minWidth: 0 }}
                      >
                        <option value="A">상태 상(A)</option>
                        <option value="B">상태 중(B)</option>
                        <option value="C">상태 하(C)</option>
                      </select>
                      <button
                        type="button" onClick={() => removeAsset(i)} className="btn"
                        style={{ width: 'auto', padding: '0 .7rem', background: '#fee2e2', color: '#b91c1c' }}
                      >삭제</button>
                    </div>
                  </div>
                ))}
                <button
                  type="button" onClick={addAsset} className="btn"
                  style={{ width: 'auto', padding: '.45rem .9rem', fontSize: '.82rem' }}
                >+ 시설 추가</button>
              </div>

              {/* 판로·매출 */}
              <div className="form-row">
                <div className="form-group">
                  <label>연 매출 (만원)</label>
                  <input
                    type="number" min="0" placeholder="예: 5000" value={annualRevenue}
                    onChange={e => setAnnualRevenue(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>주 판로</label>
                  <select value={salesChannel} onChange={e => setSalesChannel(e.target.value)}>
                    <option value="">선택 안 함</option>
                    <option value="계약재배">계약재배</option>
                    <option value="직거래">직거래</option>
                    <option value="공판장">공판장 출하</option>
                  </select>
                </div>
              </div>
              <p style={{ fontSize: '.75rem', color: 'var(--gray)' }}>
                매출·판로를 입력하면 영업권이 반영되고 신뢰등급이 올라갑니다. (자료 제출·실사 시 정밀화)
              </p>
            </div>
          )}
        </div>

        <button type="submit" className="btn btn-primary" style={{ marginTop: '1.5rem' }} disabled={loading}>
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
