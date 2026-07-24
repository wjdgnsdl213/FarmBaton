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
  A: '현장 확인까지 마친 결과', B: '제출한 자료로 계산한 결과', C: '입력한 내용으로 계산한 결과', D: '간단한 정보로 계산한 결과',
}

const SQM_PER_PYEONG = 3.305785

function formatPyeong(area: number | string | undefined) {
  const areaM2 = typeof area === 'number' ? area : Number(area)
  if (!Number.isFinite(areaM2) || areaM2 <= 0) return null
  return Math.round(areaM2 / SQM_PER_PYEONG).toLocaleString('ko-KR')
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
  const [locating, setLocating] = useState(false)
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
  const [currentStep, setCurrentStep] = useState(1)

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

  const handleCurrentLocation = () => {
    if (!navigator.geolocation) {
      setGeocodeError('이 기기에서는 현재 위치를 사용할 수 없습니다. 주소를 직접 입력해주세요.')
      return
    }
    setLocating(true)
    setGeocodeError(null)
    setGeocodeWarning(null)
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const position: [number, number] = [coords.latitude, coords.longitude]
        setMapPos(position)
        setBoundary(null)
        setParcelInfo(null)
        try {
          const res = await api.reverseGeocode(coords.latitude, coords.longitude)
          setForm(f => ({ ...f, address: res.address }))
          setGeocodeWarning('현재 위치를 주소에 반영했어요. 지도 위치가 농장과 맞는지 확인해주세요.')
        } catch {
          setGeocodeWarning('현재 위치는 지도에 표시했어요. 주소는 직접 입력해주세요.')
        } finally {
          setLocating(false)
        }
      },
      () => {
        setLocating(false)
        setGeocodeError('현재 위치를 가져오지 못했습니다. 위치 권한을 허용하거나 주소를 직접 입력해주세요.')
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    )
  }

  const moveToNextStep = () => {
    if (currentStep === 1) {
      if (!form.address.trim()) { setError('농장 주소를 입력하세요.'); return }
      if (!mapPos && !form.area_m2) {
        setError('위치를 검색해 확인하거나, 농장 면적을 직접 입력하세요.')
        return
      }
    }
    setError(null)
    setCurrentStep(step => Math.min(step + 1, 3))
  }

  const moveToPreviousStep = () => {
    setError(null)
    setCurrentStep(step => Math.max(step - 1, 1))
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
        setError(res.warning || '결과를 계산하지 못했습니다.')
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
          <span className="hero-eyebrow">내 농장 알아보기</span>
          <h1>내 농장, 넘기기 전에<br />참고할 금액을 알아보세요</h1>
          <p>주소와 키우는 과일을 알려주시면 소득·토지·시설을 살펴 금액 범위로 알려드려요.</p>
        </div>
      </header>

      <div className="page-wrap">
      <form className="card" onSubmit={handleSubmit}>
        <div className="card-title">내 농장 알려주기</div>
        <div className="farm-stepper" aria-label="농장 정보 입력 단계">
          {['농장 위치', '농장 정보', '아는 정보'].map((label, index) => {
            const step = index + 1
            return (
              <div key={label} className={`farm-stepper-item ${step === currentStep ? 'active' : step < currentStep ? 'done' : ''}`}>
                <span>{step}</span><b>{label}</b>
              </div>
            )
          })}
        </div>

        {error && <div className="error-box">{error}</div>}

        {currentStep === 1 && <section className="farm-step" aria-labelledby="farm-step-location">
        <div className="farm-step-heading">
          <h2 id="farm-step-location">농장은 어디에 있나요?</h2>
          <p>주소를 입력하고 위치를 확인해주세요.</p>
        </div>

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
          <button
            type="button"
            className="farm-current-location"
            onClick={handleCurrentLocation}
            disabled={locating}
          >
            {locating ? <span className="spinner" /> : '◎ 현재 위치로 주소 입력'}
          </button>
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
                ? ` · 농장 면적 ${parcelInfo.area_m2.toLocaleString('ko-KR')}㎡ (약 ${formatPyeong(parcelInfo.area_m2)}평) 자동 입력`
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

        <div className="form-group">
          <label>
            농장 면적
            {parcelInfo?.area_m2
              ? <span style={{ color: 'var(--green)', fontWeight: 400 }}> (자동 입력됨)</span>
              : <span style={{ color: 'var(--gray)', fontWeight: 400 }}> (직접 입력 가능)</span>}
          </label>
          <div className="farm-area-input">
            <input
              type="number" min="0" value={form.area_m2}
              onChange={set('area_m2')} placeholder="위치 검색 시 자동 입력"
            />
            <span>㎡{formatPyeong(form.area_m2) ? ` · 약 ${formatPyeong(form.area_m2)}평` : ''}</span>
          </div>
        </div>
        <div className="farm-step-actions farm-step-actions-next">
          <button type="button" className="btn btn-primary" onClick={moveToNextStep}>다음</button>
        </div>
        </section>}

        {currentStep === 2 && <section className="farm-step" aria-labelledby="farm-step-basic">
        <div className="farm-step-heading">
          <h2 id="farm-step-basic">농장에 대해 알려주세요</h2>
          <p>키우는 과일과 나무 나이, 넘기는 방법을 알려주세요.</p>
        </div>
        <div className="form-row">
          <div className="form-group">
            <label>어떤 과일을 키우시나요? *</label>
            <select value={form.crop_code} onChange={set('crop_code')}>
              <option value="APPLE">사과</option>
              <option value="PEACH">복숭아</option>
              <option value="GRAPE">포도</option>
            </select>
          </div>
          <div className="form-group">
            <label>나무를 심은 지 몇 년 됐나요?</label>
            <input type="number" min="0" max="99" value={form.tree_age} onChange={set('tree_age')} />
          </div>
        </div>

        <div className="form-group">
          <label>농장을 어떻게 넘기고 싶으신가요?</label>
          <select value={form.succession_type} onChange={set('succession_type')}>
            <option value="SALE">팔기</option>
            <option value="LEASE">빌려주기</option>
            <option value="JOINT">함께 농사짓기</option>
            <option value="MENTORING">일을 가르친 뒤 넘기기</option>
          </select>
        </div>

        <div className="farm-step-actions">
          <button type="button" className="btn btn-secondary" onClick={moveToPreviousStep}>이전</button>
          <button type="button" className="btn btn-primary" onClick={moveToNextStep}>다음</button>
        </div>
        </section>}

        {currentStep === 3 && <section className="farm-step" aria-labelledby="farm-step-optional">
        <div className="farm-step-heading">
          <h2 id="farm-step-optional">더 알려주실 내용이 있나요?</h2>
          <p>건너뛰어도 알려드릴게요.</p>
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
                시설과 판매 정보 적기 <span style={{ fontWeight: 500, color: 'var(--gray)' }}>(선택)</span>
              </span>
              <span style={{ fontSize: '.76rem', color: 'var(--gray)' }}>
                알고 계신 만큼만 적어주세요
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
                <label style={{ fontWeight: 600, fontSize: '.85rem' }}>농장에 있는 시설</label>
                {assets.length === 0 && (
                  <p style={{ fontSize: '.78rem', color: 'var(--gray)', margin: '.3rem 0' }}>
                    저온저장고·비닐하우스 등이 있으면 시설 값도 함께 계산해드려요.
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
                        type="number" min="1980" max="2026" placeholder="설치한 해 (예: 2015)" value={a.installed_year}
                        onChange={e => updateAsset(i, 'installed_year', e.target.value)}
                        style={{ flex: '1 1 80px', minWidth: 0 }}
                      />
                      <select
                        value={a.condition_grade}
                        onChange={e => updateAsset(i, 'condition_grade', e.target.value)}
                        style={{ flex: '1 1 90px', minWidth: 0 }}
                      >
                        <option value="A">상태 좋음</option>
                        <option value="B">상태 보통</option>
                        <option value="C">수리가 필요함</option>
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
                  <label>한 해 매출 (만원)</label>
                  <input
                    type="number" min="0" placeholder="예: 5000" value={annualRevenue}
                    onChange={e => setAnnualRevenue(e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label>주로 어디에 파시나요?</label>
                  <select value={salesChannel} onChange={e => setSalesChannel(e.target.value)}>
                    <option value="">선택 안 함</option>
                    <option value="계약재배">계약재배</option>
                    <option value="직거래">직거래</option>
                    <option value="공판장">공판장 출하</option>
                  </select>
                </div>
              </div>
              <p style={{ fontSize: '.75rem', color: 'var(--gray)' }}>
                매출과 판매처를 적으면 농장 운영 가치도 함께 계산해드려요.
              </p>
            </div>
          )}
        </div>

        <div className="farm-step-actions">
          <button type="button" className="btn btn-secondary" onClick={moveToPreviousStep}>이전</button>
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? <span className="spinner" /> : '내 농장 결과 보기'}
          </button>
        </div>
        </section>}
      </form>

      {result && (
        <div className="card scroll-anchor" ref={resultRef}>
          <div className="card-title">
            인수 검토가 범위(참고용 추정)&nbsp;
            <span className="grade-badge">
              {GRADE_DESC[result.confidence_grade]}
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
              <div className="val-item-label">토지 기준 금액</div>
              <div className="val-item-value">{fmt(result.land_value_point)}만원</div>
            </div>
            <div className="val-item">
              <div className="val-item-label">시설의 현재 가치</div>
              <div className="val-item-value">{fmt(result.facility_value)}만원</div>
            </div>
            <div className="val-item">
              <div className="val-item-label">매출·판매처 가치</div>
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
              ✓ 농장이 청년농에게 공개되었습니다.
            </div>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              style={{ marginTop: '.8rem' }}
              onClick={handlePublish}
              disabled={publishState === 'publishing'}
            >
              {publishState === 'publishing' ? <span className="spinner" /> : '청년농에게 농장 공개하기'}
            </button>
          )}
          {publishState === 'error' && (
            <div className="error-box" style={{ marginTop: '.5rem' }}>농장 공개에 실패했습니다. 다시 눌러주세요.</div>
          )}
          <p style={{ fontSize: '.78rem', color: 'var(--gray)', margin: '.4rem 0 0' }}>
            지금 공개하지 않아도 저장됩니다. 결과는 언제든 다시 볼 수 있어요.
          </p>

          <a
            href={api.reportPdfUrl(result.farm_id, 'farmer')}
            className="btn btn-primary"
            style={{ display: 'block', textAlign: 'center', marginTop: '.6rem', textDecoration: 'none' }}
            target="_blank"
            rel="noopener noreferrer"
          >
            결과표 PDF로 받기
          </a>
        </div>
      )}
      </div>
    </div>
  )
}
