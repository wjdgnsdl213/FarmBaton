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
    role: str = Field(default="FARMER", pattern="^(FARMER|YOUNG)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    token: str
    user_id: int
    name: str
    role: str


class MeResponse(BaseModel):
    user_id: int
    name: str
    email: str
    role: str
    phone: Optional[str] = None


class UpdateMeRequest(BaseModel):
    name: str = Field(min_length=1)
    phone: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


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


class FarmSummary(BaseModel):
    id: int
    address: str
    sido: str
    crop_code: str
    area_m2: float
    status: str
    est_value_min: Optional[int]
    est_value_max: Optional[int]


class FarmStatusUpdate(BaseModel):
    status: str = Field(pattern="^(DRAFT|ACTIVE)$")


class FarmStatusUpdateResponse(BaseModel):
    id: int
    status: str


# ── 상담 신청 ────────────────────────────────────────────────────────────────

class ConsultRequestCreate(BaseModel):
    young_farmer_id: int
    message: Optional[str] = None


class ConsultRequestResponse(BaseModel):
    id: int
    status: str
    farm_status: Optional[str] = None


class ConsultRequestDetail(BaseModel):
    """농장주 상담함 1건 — 신청한 청년농의 매칭 프로필·점수 포함."""
    id: int
    farm_id: int
    young_farmer_id: int
    applicant_name: Optional[str]      # 청년농 계정 이름 (전화번호는 노출하지 않음)
    message: Optional[str]
    status: str
    created_at: str
    # 매칭 프로필 (calc_match_score 재사용)
    pref_sido: Optional[str]
    pref_crop: Optional[str]
    available_capital: int             # 만원
    experience_years: int
    pref_succession: str
    policy_fund: bool
    total_score: float
    intro: Optional[str] = None


class ConsultRequestStatusUpdate(BaseModel):
    status: str = Field(pattern="^(ACCEPTED|DECLINED)$")


# ── 채팅 ────────────────────────────────────────────────────────────────────

class ChatMessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class ChatMessageItem(BaseModel):
    id: int
    sender_role: str          # FARMER | YOUNG
    body: str
    created_at: str
    mine: bool                # 요청자 기준 내가 보낸 메시지인지


class ChatThreadResponse(BaseModel):
    consult_request_id: int
    status: str               # consult_request.status — ACCEPTED일 때만 전송 가능
    chat_enabled: bool        # status == ACCEPTED
    counterpart_name: str     # 상대 표시명 (농장주↔청년농)
    farm_label: str
    messages: list[ChatMessageItem]


class ConversationItem(BaseModel):
    """대화 목록 1건 — 역할 무관, 수락된 상담 = 대화방."""
    consult_request_id: int
    farm_id: int
    farm_label: str
    counterpart_name: str     # 농장주에겐 청년농 이름, 청년농에겐 농장주 이름
    initiated_by: str         # YOUNG | FARMER
    last_message_at: Optional[str]
    last_message_preview: Optional[str]


class FarmerInitiateConversation(BaseModel):
    young_farmer_id: int


# ── 청년농 본인 상담함 ────────────────────────────────────────────────────────

class MyConsultRequestItem(BaseModel):
    id: int
    farm_id: int
    farm_label: str           # 예: "충북 사과 농장"
    address: str
    est_value_min: Optional[int]
    est_value_max: Optional[int]
    status: str
    created_at: str


class FarmCreateResponse(BaseModel):
    farm_id: int
    valuation: Optional[ValuationResponse] = None
    warning: Optional[str] = None


# ── 청년농 등록 요청 ──────────────────────────────────────────────────────────

class YoungFarmerCreate(BaseModel):
    # 매칭 검색 입력값 (미저장 — /match-search). 프로필을 덮어쓰지 않는다.
    pref_sido: Optional[str] = None    # None = 지역 상관없음
    pref_crop: Optional[str] = Field(default=None, pattern="^(APPLE|PEACH|GRAPE)$")  # None = 작목 상관없음
    available_capital: float = Field(ge=0)
    experience_years: int = Field(ge=0)
    policy_fund: bool = False
    pref_succession: str = Field(pattern="^(SALE|LEASE|JOINT|MENTORING)$")


class YoungFarmerCreateResponse(BaseModel):
    young_farmer_id: int


class YoungProfileData(BaseModel):
    """청년농 실제 프로필 (내 정보에서 설정 → 상담 시 농장주에게 노출).

    매칭 '검색'과 분리된, 청년농의 진짜 정보. available_capital은 원 단위.
    """
    young_farmer_id: Optional[int] = None   # GET 응답용 (프로필 없으면 None)
    pref_sido: Optional[str] = None
    pref_crop: Optional[str] = Field(default=None, pattern="^(APPLE|PEACH|GRAPE)$")
    available_capital: float = Field(default=0, ge=0)
    experience_years: int = Field(default=0, ge=0)
    policy_fund: bool = False
    pref_succession: str = Field(default="SALE", pattern="^(SALE|LEASE|JOINT|MENTORING)$")
    intro: Optional[str] = None


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


class FarmMatchItem(BaseModel):
    """농장주 화면용 — 이 농장에 매칭되는 청년농 1명."""
    young_farmer_id: int
    pref_sido: Optional[str]
    pref_crop: Optional[str]
    available_capital: int  # 만원
    experience_years: int
    pref_succession: str
    policy_fund: bool
    total_score: float
    region_score: float
    crop_score: float
    capital_score: float
    experience_score: float
    succession_score: float
    policy_score: float
    risk_penalty: float
    explanation: Optional[str] = None
    intro: Optional[str] = None


class FarmMatchListResponse(BaseModel):
    farm_id: int
    matches: list[FarmMatchItem]


# ── 지원사업 추천 ─────────────────────────────────────────────────────────────

class SupportProgramItem(BaseModel):
    program_code: str
    name: str
    description: str
    amount_text: str
    apply_url: Optional[str]
    pitch: Optional[str] = None   # AI 생성 추천 사유 1문장 (사실 정보는 위 필드 그대로)


class SupportProgramListResponse(BaseModel):
    young_farmer_id: int
    programs: list[SupportProgramItem]
