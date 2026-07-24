import axios from 'axios'

// 개발: Vite 프록시(/api → localhost:8000)
// 배포: VITE_API_BASE_URL=https://your-backend.railway.app/api
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const client = axios.create({
  baseURL: API_BASE_URL,
})

const TOKEN_KEY = 'farmbaton_token'
const ROLE_KEY = 'farmbaton_role'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const getRole = () => localStorage.getItem(ROLE_KEY)
export const setRole = (role: string) => localStorage.setItem(ROLE_KEY, role)
export const clearToken = () => {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(ROLE_KEY)
}

client.interceptors.request.use(config => {
  const token = getToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

export interface FarmCreatePayload {
  address: string
  lon?: number
  lat?: number
  crop_code: string
  tree_age: number
  area_m2?: number
  succession_type?: string
  timing?: string
  annual_revenue?: number          // 원 단위 (선택) — 영업권·숙련도 보정
  revenue_years?: 1 | 3            // 제출한 매출 자료 기간
  sales_channel?: string           // 계약재배 / 직거래 / 공판장 (선택)
  assets?: { facility_code: string; area_m2: number; installed_year?: number; condition_grade: string }[]
}

export interface FacilityOption {
  facility_code: string
  label: string
}

export interface ValuationResult {
  farm_id: number
  confidence_grade: string
  est_income_min: number
  est_income_max: number
  est_value_min: number
  est_value_max: number
  income_point: number
  income_adjustment_pct: number
  revenue_cap_applied: boolean
  land_value_point: number
  facility_value: number
  facility_value_krw: number
  goodwill_min: number
  goodwill_max: number
  label: string
  disclaimer: string
}

export interface FarmCreateResult {
  farm_id: number
  valuation: ValuationResult | null
  warning: string | null
}

export interface MatchItem {
  farm_id: number
  address: string
  sido: string
  crop_code: string
  tree_age: number | null
  area_m2: number
  succession_type: string | null
  est_value_min: number
  est_value_max: number
  total_score: number
  region_score: number
  crop_score: number
  capital_score: number
  experience_score: number
  succession_score: number
  policy_score: number
  risk_penalty: number
  explanation: string | null
  disclaimer: string
}

export interface MatchListResult {
  young_farmer_id: number
  matches: MatchItem[]
  other_crop_matches: MatchItem[]
}

export interface FarmMatchItem {
  young_farmer_id: number
  pref_sido: string | null
  pref_crop: string | null
  available_capital: number
  experience_years: number
  pref_succession: string
  policy_fund: boolean
  total_score: number
  region_score: number
  crop_score: number
  capital_score: number
  experience_score: number
  succession_score: number
  policy_score: number
  risk_penalty: number
  explanation: string | null
  intro: string | null
}

export interface FarmMatchListResult {
  farm_id: number
  matches: FarmMatchItem[]
}

export interface YoungFarmerPayload {
  pref_sido?: string | null
  pref_crop?: string | null
  available_capital: number
  experience_years: number
  policy_fund: boolean
  pref_succession: string
}

export interface YoungProfile {
  young_farmer_id: number | null
  pref_sido: string | null
  pref_crop: string | null
  available_capital: number   // 원
  experience_years: number
  policy_fund: boolean
  pref_succession: string
  intro: string | null
}

export interface GeocodeResult {
  lon: number
  lat: number
  area_m2?: number
  sido?: string
  sigungu?: string
  boundary?: GeoJSON.Geometry
  warning?: string
}

export interface ReverseGeocodeResult {
  address: string
  lon: number
  lat: number
  source: 'vworld' | 'static'
}

export interface AssetSummary {
  facility_code: string
  facility_name: string
  area_m2: number
  installed_year: number | null
  condition_grade: string
}

export interface FarmDetail {
  id: number
  address: string
  sido: string
  crop_code: string
  tree_age: number | null
  area_m2: number
  succession_type: string | null
  est_value_min: number | null
  est_value_max: number | null
  confidence_grade: string | null
  status: string
  is_demo: boolean
  assets: AssetSummary[]
}

export interface ConsultRequestPayload {
  young_farmer_id: number
  message?: string | null
}

export interface ConsultRequestResult {
  id: number
  status: string
  farm_status?: string | null
}

export interface ConsultRequestDetail {
  id: number
  farm_id: number
  young_farmer_id: number
  applicant_name: string | null
  message: string | null
  status: string
  created_at: string
  pref_sido: string | null
  pref_crop: string | null
  available_capital: number
  experience_years: number
  pref_succession: string
  policy_fund: boolean
  total_score: number
  intro: string | null
}

export interface ChatMessageItem {
  id: number
  sender_role: string
  body: string
  created_at: string
  mine: boolean
}

export interface ChatThread {
  consult_request_id: number
  status: string
  chat_enabled: boolean
  counterpart_name: string
  farm_label: string
  messages: ChatMessageItem[]
}

export interface ConversationItem {
  consult_request_id: number
  farm_id: number
  farm_label: string
  counterpart_name: string
  initiated_by: string
  last_message_at: string | null
  last_message_preview: string | null
}

export interface MyConsultRequest {
  id: number
  farm_id: number
  farm_label: string
  address: string
  est_value_min: number | null
  est_value_max: number | null
  status: string
  created_at: string
}

export interface FarmSummary {
  id: number
  address: string
  sido: string
  crop_code: string
  area_m2: number
  status: string
  est_value_min: number | null
  est_value_max: number | null
}

export interface RegisterPayload {
  email: string
  password: string
  name: string
  phone?: string
  role: 'FARMER' | 'YOUNG'
}

export interface LoginPayload {
  email: string
  password: string
}

export interface AuthResult {
  token: string
  user_id: number
  name: string
  role: string
}

export interface MeResult {
  user_id: number
  name: string
  email: string
  role: string
  phone?: string | null
}

export interface SupportProgramItem {
  program_code: string
  name: string
  description: string
  amount_text: string
  apply_url: string | null
  pitch: string | null
}

export interface SupportProgramListResult {
  young_farmer_id: number
  programs: SupportProgramItem[]
}

export const api = {
  geocode: (address: string, crop_code = 'APPLE') =>
    client.get<GeocodeResult>('/geocode', { params: { address, crop_code } }).then(r => r.data),

  reverseGeocode: (lat: number, lon: number) =>
    client.get<ReverseGeocodeResult>('/reverse-geocode', { params: { lat, lon } }).then(r => r.data),

  reportPdfUrl: (farmId: number, audience: 'farmer' | 'young' = 'farmer') =>
    `${API_BASE_URL}/farms/${farmId}/report.pdf?audience=${audience}`,

  createFarm: (data: FarmCreatePayload) =>
    client.post<FarmCreateResult>('/farms', data).then(r => r.data),

  facilities: () =>
    client.get<FacilityOption[]>('/facilities').then(r => r.data),

  getValuation: (farmId: number) =>
    client.get<ValuationResult>(`/farms/${farmId}/valuation`).then(r => r.data),

  // 매칭 검색 (탐색용, 미저장). 응답 young_farmer_id = 본인 실제 프로필 id(상담용)
  matchSearch: (data: YoungFarmerPayload) =>
    client.post<MatchListResult>('/young-farmers/match-search', data).then(r => r.data),

  // 청년농 실제 프로필 (내 정보)
  getMyProfile: () =>
    client.get<YoungProfile>('/young-farmers/me/profile').then(r => r.data),

  putMyProfile: (data: Omit<YoungProfile, 'young_farmer_id'>) =>
    client.put<YoungProfile>('/young-farmers/me/profile', data).then(r => r.data),

  getSupportPrograms: (yfId: number, farmId?: number) =>
    client.get<SupportProgramListResult>(`/young-farmers/${yfId}/support-programs`, {
      params: farmId ? { farm_id: farmId } : undefined,
    }).then(r => r.data),

  getFarmDetail: (farmId: number) =>
    client.get<FarmDetail>(`/farms/${farmId}`).then(r => r.data),

  createConsultRequest: (farmId: number, data: ConsultRequestPayload) =>
    client.post<ConsultRequestResult>(`/farms/${farmId}/consult-requests`, data).then(r => r.data),

  register: (data: RegisterPayload) =>
    client.post<AuthResult>('/auth/register', data).then(r => r.data),

  login: (data: LoginPayload) =>
    client.post<AuthResult>('/auth/login', data).then(r => r.data),

  getMe: () =>
    client.get<MeResult>('/auth/me').then(r => r.data),

  updateMe: (data: { name: string; phone?: string | null }) =>
    client.patch<MeResult>('/auth/me', data).then(r => r.data),

  changePassword: (current_password: string, new_password: string) =>
    client.post('/auth/password', { current_password, new_password }).then(r => r.data),

  getMyFarms: () =>
    client.get<FarmSummary[]>('/farms/mine').then(r => r.data),

  getConsultRequests: (farmId: number) =>
    client.get<ConsultRequestDetail[]>(`/farms/${farmId}/consult-requests`).then(r => r.data),

  updateConsultRequestStatus: (farmId: number, reqId: number, status: 'ACCEPTED' | 'DECLINED') =>
    client.patch<ConsultRequestResult>(`/farms/${farmId}/consult-requests/${reqId}`, { status }).then(r => r.data),

  updateFarmStatus: (farmId: number, status: 'DRAFT' | 'ACTIVE') =>
    client.patch<{ id: number; status: string }>(`/farms/${farmId}/status`, { status }).then(r => r.data),

  getFarmMatches: (farmId: number) =>
    client.get<FarmMatchListResult>(`/farms/${farmId}/matches`).then(r => r.data),

  // ── 채팅 ──
  getChatThread: (reqId: number) =>
    client.get<ChatThread>(`/consult-requests/${reqId}/messages`).then(r => r.data),

  sendChatMessage: (reqId: number, body: string) =>
    client.post<ChatMessageItem>(`/consult-requests/${reqId}/messages`, { body }).then(r => r.data),

  // ── 청년농 본인 상담함 ──
  getMyConsultRequests: () =>
    client.get<MyConsultRequest[]>('/young-farmers/me/consult-requests').then(r => r.data),

  // ── 대화 목록 (역할 무관) ──
  getConversations: () =>
    client.get<ConversationItem[]>('/conversations').then(r => r.data),

  // ── 농장주 발신 대화 시작 ──
  initiateConversation: (farmId: number, youngFarmerId: number) =>
    client.post<ConsultRequestResult>(`/farms/${farmId}/conversations`, { young_farmer_id: youngFarmerId }).then(r => r.data),

  deleteConversation: (reqId: number) =>
    client.delete(`/conversations/${reqId}`).then(r => r.data),
}
