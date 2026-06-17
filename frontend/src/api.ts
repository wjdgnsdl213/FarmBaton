import axios from 'axios'

const client = axios.create({ baseURL: '/api' })

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
  disclaimer: string
}

export interface MatchListResult {
  young_farmer_id: number
  matches: MatchItem[]
}

export interface YoungFarmerPayload {
  pref_sido: string
  pref_crop: string
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

export const api = {
  geocode: (address: string, crop_code = 'APPLE') =>
    client.get<GeocodeResult>('/geocode', { params: { address, crop_code } }).then(r => r.data),

  createFarm: (data: FarmCreatePayload) =>
    client.post<FarmCreateResult>('/farms', data).then(r => r.data),

  getValuation: (farmId: number) =>
    client.get<ValuationResult>(`/farms/${farmId}/valuation`).then(r => r.data),

  createYoungFarmer: (data: YoungFarmerPayload) =>
    client.post<{ young_farmer_id: number }>('/young-farmers', data).then(r => r.data),

  getMatches: (yfId: number) =>
    client.get<MatchListResult>(`/young-farmers/${yfId}/matches`).then(r => r.data),
}
