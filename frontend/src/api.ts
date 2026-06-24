import axios from 'axios'

// 개발: Vite 프록시(/api → localhost:8000)
// 배포: VITE_API_BASE_URL=https://your-backend.railway.app/api
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '/api'

const client = axios.create({
  baseURL: API_BASE_URL,
})

const TOKEN_KEY = 'farmbaton_token'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token)
export const clearToken = () => localStorage.removeItem(TOKEN_KEY)

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
  assets?: { facility_code: string; area_m2: number; installed_year?: number; condition_grade: string }[]
}

export interface ValuationResult {
  farm_id: number
  confidence_grade: string
  est_income_min: number
  est_income_max: number
  est_value_min: number
  est_value_max: number
  income_point: number
  land_value_point: number
  facility_value: number
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

export interface GeocodeResult {
  lon: number
  lat: number
  area_m2?: number
  sido?: string
  sigungu?: string
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
  contact_name?: string | null
  contact_phone?: string | null
}

export interface ConsultRequestResult {
  id: number
  status: string
  farm_status?: string | null
}

export interface ConsultRequestDetail {
  id: number
  farm_id: number
  contact_name: string | null
  contact_phone: string | null
  message: string | null
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
}

export interface LoginPayload {
  email: string
  password: string
}

export interface AuthResult {
  token: string
  user_id: number
  name: string
}

export interface MeResult {
  user_id: number
  name: string
  email: string
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

  reportPdfUrl: (farmId: number, audience: 'farmer' | 'young' = 'farmer') =>
    `${API_BASE_URL}/farms/${farmId}/report.pdf?audience=${audience}`,

  createFarm: (data: FarmCreatePayload) =>
    client.post<FarmCreateResult>('/farms', data).then(r => r.data),

  getValuation: (farmId: number) =>
    client.get<ValuationResult>(`/farms/${farmId}/valuation`).then(r => r.data),

  createYoungFarmer: (data: YoungFarmerPayload) =>
    client.post<{ young_farmer_id: number }>('/young-farmers', data).then(r => r.data),

  getMatches: (yfId: number) =>
    client.get<MatchListResult>(`/young-farmers/${yfId}/matches`).then(r => r.data),

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
}
