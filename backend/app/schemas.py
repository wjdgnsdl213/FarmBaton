"""Pydantic v2 요청/응답 스키마."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, EmailStr, Field

# ── 농가 인증 ────────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str
    phone: Optional[str] = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: int
    name: str


class MeResponse(BaseModel):
    user_id: int
    name: str
    email: str


# ── 농가 등록 요청 ────────────────────────────────────────────────────────────

class AssetCreate(BaseModel):
    facility_code: str
    area_m2: float = Field(gt=0)
    installed_year: Optional[int] = None
    condition_grade: str = Field(default="B", pattern="^[ABC]$")


class FarmCreate(BaseModel):
    address: str
    lon: Optional[float] = None    # 지오코딩 결과 경도 (WGS84)
    lat: Optional[float] = None    # 지오코딩 결과 위도
    crop_code: str = Field(pattern="^(APPLE|PEACH|GRAPE)$")
    tree_age: int = Field(ge=0)
    area_m2: Optional[float] = Field(default=None, gt=0)  # lon/lat 없을 때 필수
    succession_type: Optional[str] = Field(
        default=None, pattern="^(SALE|LEASE|JOINT|MENTORING)$"
    )
    timing: Optional[str] = Field(
        default=None, pattern="^(NOW|WITHIN_1Y|WITHIN_3Y|WITHIN_5Y)$"
    )
    annual_revenue: Optional[float] = Field(default=None, ge=0)
    sales_channel: Optional[str] = None   # 계약재배/직거래/공판장
    assets: list[AssetCreate] = []
    is_demo: bool = False


# ── 가치평가 결과 응답 ────────────────────────────────────────────────────────

DISCLAIMER = (
    "이 수치는 공공데이터 기반 사전 검토용 추정값이며, "
    "법적 효력이 있는 감정평가가 아닙니다. "
    "실제 거래 시 공인 감정평가사 또는 공인중개사 검토를 권장합니다."
)


class ValuationResponse(BaseModel):
    farm_id: int
    confidence_grade: str
    est_income_min: int       # 만원 반올림
    est_income_max: int
    est_value_min: int        # 만원 반올림 (인수 검토가 범위 하한)
    est_value_max: int        # 만원 반올림 (인수 검토가 범위 상한)
    income_point: int
    land_value_point: int
    facility_value: int
    goodwill_min: int
    goodwill_max: int
    label: str = "인수 검토가 범위(참고용 추정)"
    disclaimer: str = DISCLAIMER


# ── 농장 상세 응답 ────────────────────────────────────────────────────────────

class AssetSummary(BaseModel):
    facility_code: str
    facility_name: str
    area_m2: float
    installed_year: Optional[int]
    condition_grade: str


class FarmDetail(BaseModel):
    id: int
    address: str
    sido: str
    crop_code: str
    tree_age: Optional[int]
    area_m2: float
    succession_type: Optional[str]
    est_value_min: Optional[int]
    est_value_max: Optional[int]
    confidence_grade: Optional[str]
    status: str
    is_demo: bool
    assets: list[AssetSummary] = []


# ── 상담 신청 ────────────────────────────────────────────────────────────────

class ConsultRequestCreate(BaseModel):
    young_farmer_id: int
    message: Optional[str] = None


class ConsultRequestResponse(BaseModel):
    id: int
    status: str


class FarmCreateResponse(BaseModel):
    farm_id: int
    valuation: Optional[ValuationResponse] = None
    warning: Optional[str] = None


# ── 청년농 등록 요청 ──────────────────────────────────────────────────────────

class YoungFarmerCreate(BaseModel):
    pref_sido: Optional[str] = None    # None = 지역 상관없음
    pref_crop: Optional[str] = Field(default=None, pattern="^(APPLE|PEACH|GRAPE)$")  # None = 작목 상관없음
    available_capital: float = Field(ge=0)
    experience_years: int = Field(ge=0)
    policy_fund: bool = False
    pref_succession: str = Field(pattern="^(SALE|LEASE|JOINT|MENTORING)$")


class YoungFarmerCreateResponse(BaseModel):
    young_farmer_id: int


# ── 매칭 결과 응답 ────────────────────────────────────────────────────────────

class MatchItem(BaseModel):
    farm_id: int
    address: str
    sido: str
    crop_code: str
    tree_age: Optional[int]
    area_m2: float
    succession_type: Optional[str]
    est_value_min: int   # 만원
    est_value_max: int
    total_score: float
    region_score: float
    crop_score: float
    capital_score: float
    experience_score: float
    succession_score: float
    policy_score: float
    risk_penalty: float
    explanation: Optional[str] = None
    label: str = "인수 검토가 범위(참고용 추정)"
    disclaimer: str = DISCLAIMER


class MatchListResponse(BaseModel):
    young_farmer_id: int
    matches: list[MatchItem]
