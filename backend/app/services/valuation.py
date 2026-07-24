"""
backend/app/services/valuation.py

가치평가·매칭 순수 함수 모음 (formula.md §1-7 구현).

모든 계수·단가는 호출 전에 DB에서 조회하여 FarmInput/AssetData에 주입한다.
이 모듈 안에서는 DB 호출 없이 결정론적 계산만 수행한다. LLM 호출 절대 금지.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Optional

# ── 공개 상수 ────────────────────────────────────────────────────────────────

INCOME_BAND: dict[str, float] = {"A": 0.08, "B": 0.12, "C": 0.18, "D": 0.25}
OFFICIAL_TO_MARKET: float = 0.65
POLICY_FUND_LIMIT: float = 500_000_000.0  # 청년창업농 융자 한도 (원)

# APPLE은 기술 난이도가 높은 작목 (밀식재배 관리 등) — 매칭 점수 계산에 사용
HIGH_DIFFICULTY_CROPS: set[str] = {"APPLE"}

# 경제수령 상한 — orchard_age_coef 성목기 상단과 일치해야 함 (DB 변경 시 동기화)
_ECONOMIC_LIFE: dict[str, int] = {"APPLE": 20, "PEACH": 15, "GRAPE": 18}

# 시설 상태 승수 — facility_condition 테이블과 일치
_CONDITION_MULT: dict[str, float] = {"A": 1.00, "B": 0.85, "C": 0.60}

# 승계방식 호환 점수 (부분점수 8점)
_SUCCESSION_COMPAT: dict[tuple[str, str], float] = {
    ("JOINT", "MENTORING"): 8.0,
    ("MENTORING", "JOINT"): 8.0,
    ("LEASE", "JOINT"): 8.0,
    ("JOINT", "LEASE"): 8.0,
}


# ── 데이터 클래스 ─────────────────────────────────────────────────────────────

@dataclass
class LandData:
    """토지 가격 정보 (fn_farm_card 또는 land_price 조회 결과)."""
    area_m2: float
    official_price_m2: float
    deal_price_m2: Optional[float] = None
    deal_sample_cnt: int = 0


@dataclass
class AssetData:
    """시설 자산 1건 (farm_asset 행 + facility_std 조회 결과)."""
    facility_code: str
    area_m2: float
    installed_year: Optional[int]
    condition_grade: str           # "A" | "B" | "C"
    std_unit_cost_krw: float       # facility_std.std_unit_cost_krw
    useful_life_years: int         # facility_std.useful_life_years
    salvage_rate: float            # facility_std.salvage_rate
    facility_name: Optional[str] = None


@dataclass
class FarmInput:
    """가치평가 입력. 계수·단가는 DB 조회 후 주입."""
    crop_code: str
    tree_age: int
    area_m2: float
    income_10a: float              # income_coef.avg_income_10a
    age_coef: float                # orchard_age_coef.yield_coef
    trend_index: float             # price_trend.trend_index (평년=1.0)
    land: LandData
    assets: list[AssetData] = field(default_factory=list)
    gross_revenue_10a: Optional[float] = None  # income_coef.avg_gross_10a
    # 영업권 입력 (선택)
    annual_revenue: Optional[float] = None
    revenue_years: int = 0         # 0: 미제출, 1: 1년, 3: 3년
    has_contract: bool = False
    has_direct_sales: bool = False


@dataclass
class YoungFarmerInput:
    """매칭 청년농 입력. pref_sido/pref_crop이 None이면 "상관없음"으로 간주."""
    pref_sido: Optional[str]
    pref_crop: Optional[str]
    available_capital: float
    experience_years: float
    policy_fund: bool
    pref_succession: str


@dataclass
class FarmProfileForMatch:
    """매칭 농장 프로필."""
    sido: str
    crop_code: str
    succession_type: str
    est_value_min: float
    crop_difficulty_high: bool = False


# ── 결과 타입 ────────────────────────────────────────────────────────────────

@dataclass
class IncomeResult:
    point: float
    min: float
    max: float
    adjustment: float = 1.0
    cap_applied: bool = False


class LandValueResult(NamedTuple):
    """토지 기준가 결과. 속성(.point/.min/.max)과 언패킹 모두 지원."""
    point: float
    min: float
    max: float


@dataclass
class ValuationResult:
    est_income_min: float
    est_income_max: float
    est_value_min: float
    est_value_max: float
    confidence_grade: str
    income_point: float = 0.0
    land_value_point: float = 0.0
    facility_value: float = 0.0
    goodwill_min: float = 0.0
    goodwill_max: float = 0.0
    income_adjustment: float = 1.0
    revenue_cap_applied: bool = False


@dataclass
class MatchResult:
    total_score: float
    region_score: float
    crop_score: float
    capital_score: float
    experience_score: float
    succession_score: float
    policy_score: float
    risk_penalty: float


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ── 공개 함수 ────────────────────────────────────────────────────────────────

def grade_confidence(farm: FarmInput) -> str:
    """신뢰도 등급 (formula.md §6).

    매출자료와 설치연도가 확인된 시설자료가 모두 있으면 B, 아니면 C에서 시작.
    A는 사진·권리관계·현장 실사까지 필요한 단계라 현재 자동 산출하지 않는다.
    하향 트리거 1건당 1단계 down, 최저 D.
    - 실거래 부실 (공시지가만 OR 표본<3): 한 단계 down
    - installed_year 결측 자산 존재: 한 단계 down
    """
    _GRADES = ["A", "B", "C", "D"]
    has_revenue_evidence = farm.annual_revenue is not None and farm.revenue_years >= 1
    has_complete_facility_data = bool(farm.assets) and all(
        a.installed_year is not None for a in farm.assets
    )
    idx = 1 if (has_revenue_evidence and has_complete_facility_data) else 2

    if farm.land.deal_price_m2 is None or (farm.land.deal_sample_cnt or 0) < 3:
        idx += 1

    if any(a.installed_year is None for a in farm.assets):
        idx += 1

    return _GRADES[min(idx, 3)]


def grade_reasons(farm: FarmInput) -> dict:
    """신뢰등급 하향 사유와 누락 데이터 (표현용 — 계산 불변).

    grade_confidence와 동일 조건을 재사용해 "왜 이 등급인지"를 사람이 읽을
    형태로 반환한다. 어떤 수치도 바꾸지 않으며 PDF/리포트 표현에만 쓴다.
    """
    downgrades: list[str] = []
    missing: list[str] = []

    if farm.land.deal_price_m2 is None or (farm.land.deal_sample_cnt or 0) < 3:
        downgrades.append("인근 실거래 표본 부족 — 공시지가 기반으로 토지가를 추정")
        missing.append("최근 실거래가 (인근 3건 이상)")

    if any(a.installed_year is None for a in farm.assets):
        downgrades.append("일부 시설 설치연도 미상 — 잔존가를 보수적으로 추정")
        missing.append("시설 설치연도")

    return {"downgrades": downgrades, "missing": missing}


def derive_risk_flags(farm: FarmInput) -> list[str]:
    """리스크 플래그 (사람이 읽을 한국어 문구).

    calc_total_value의 신뢰도 하향·리스크 할인 트리거와 동일한 조건을
    재사용해 추출한다 — 판단은 100% 결정론적이며, LLM은 이 리스트를
    문장으로 풀어쓰는 데만 쓴다 (report_ai.generate_narrative).
    """
    flags: list[str] = []

    if farm.land.deal_price_m2 is None or (farm.land.deal_sample_cnt or 0) < 3:
        flags.append("실거래 표본 부족 — 공시지가 기반 추정")

    if any(a.installed_year is None for a in farm.assets):
        flags.append("일부 시설 설치연도 미상 — 잔존가 보수적 추정")

    eco_life = _ECONOMIC_LIFE.get(farm.crop_code, 20)
    if farm.tree_age > eco_life:
        flags.append("경제수령 초과 — 갱신 비용 고려 필요")

    return flags


def calc_income(farm: FarmInput) -> IncomeResult:
    """예상 연소득 점추정·범위 (formula.md §1).

    area_m2=0 또는 age_coef=0 이면 0 반환 (ZeroDivision 없음).
    """
    if farm.area_m2 == 0 or farm.age_coef == 0:
        return IncomeResult(point=0.0, min=0.0, max=0.0)

    base_income = farm.income_10a * (farm.area_m2 / 1_000.0)
    cap_applied = False

    if (
        farm.annual_revenue is not None
        and farm.gross_revenue_10a is not None
        and farm.gross_revenue_10a > 0
        and base_income > 0
    ):
        # 사용자가 입력하는 값은 매출(조수입), base_income은 농업소득이므로
        # 작목별 평균 소득률을 적용해 동일 단위로 환산한 뒤 비교한다.
        income_rate = farm.income_10a / farm.gross_revenue_10a
        observed_income = farm.annual_revenue * income_rate
        raw_adj = observed_income / base_income
        skill_adj = _clamp(raw_adj, 0.7, 1.3)
        cap_applied = raw_adj < 0.7 or raw_adj > 1.3
    else:
        skill_adj = 1.0

    point = base_income * farm.age_coef * farm.trend_index * skill_adj

    band = INCOME_BAND[grade_confidence(farm)]
    return IncomeResult(
        point=point,
        min=point * (1.0 - band),
        max=point * (1.0 + band),
        adjustment=skill_adj,
        cap_applied=cap_applied,
    )


def calc_land_value(land: LandData) -> LandValueResult:
    """토지 기준가 (formula.md §2).

    Returns LandValueResult(point, min, max).
    실거래가 있으면 그대로, 없으면 official / OFFICIAL_TO_MARKET 보정.
    """
    unit = (
        land.deal_price_m2
        if land.deal_price_m2 is not None
        else land.official_price_m2 / OFFICIAL_TO_MARKET
    )
    point = land.area_m2 * unit
    return LandValueResult(point=point, min=point * 0.9, max=point * 1.1)


def calc_asset_residual(asset: AssetData, current_year: int) -> float:
    """시설 자산 1건의 잔존가 (formula.md §3).

    installed_year 결측 시 dep_ratio=0.5 가정.
    """
    new_cost = asset.std_unit_cost_krw * asset.area_m2

    if asset.installed_year is None:
        dep_ratio = 0.5
    else:
        elapsed = current_year - asset.installed_year
        dep_ratio = max(asset.salvage_rate, 1.0 - elapsed / asset.useful_life_years)

    cond_mult = _CONDITION_MULT.get(asset.condition_grade, 1.0)
    return new_cost * dep_ratio * cond_mult


def calc_facility_value(
    assets: list[AssetData], current_year: int
) -> tuple[float, float, float]:
    """시설 잔존가 합산 (formula.md §3).

    Returns (total, min, max).
    """
    total = sum(calc_asset_residual(a, current_year) for a in assets)
    return total, total * 0.85, total * 1.05


def calc_goodwill(
    income_point: float,
    revenue_years: int,
    annual_revenue: Optional[float] = None,
    has_contract: bool = False,
    has_direct_sales: bool = False,
) -> tuple[float, float]:
    """영업권 (formula.md §4).

    Returns (goodwill_min, goodwill_max).
    revenue_years: 0=미제출, 1=1년, 3이상=3년.
    """
    판로_premium = min(
        (0.3 if has_contract else 0.0) + (0.2 if has_direct_sales else 0.0),
        0.5,
    )
    adder = income_point * 판로_premium

    if revenue_years >= 3:
        gw_min = income_point * 1.0 + adder
        gw_max = income_point * 2.0 + adder
    elif revenue_years == 1:
        pt = income_point * 0.5 + adder
        gw_min = gw_max = pt
    else:
        gw_min = gw_max = 0.0

    return gw_min, gw_max


def calc_total_value(farm: FarmInput, current_year: int) -> ValuationResult:
    """인수 검토가 범위 (formula.md §5).

    서브 계산 통합 → ValuationResult 반환.
    value_min 하한은 land_min (나무·시설 음수 기여 방지).
    """
    grade = grade_confidence(farm)
    income_res = calc_income(farm)
    land_val = calc_land_value(farm.land)
    fac_total, fac_min, fac_max = calc_facility_value(farm.assets, current_year)
    gw_min, gw_max = calc_goodwill(
        income_point=income_res.point,
        revenue_years=farm.revenue_years,
        annual_revenue=farm.annual_revenue,
        has_contract=farm.has_contract,
        has_direct_sales=farm.has_direct_sales,
    )

    # 리스크 할인 (disc_max → value_min 차감 / disc_min → value_max 차감)
    disc_min = 0.0
    disc_max = 0.0

    # ① installed_year 결측 자산 → 시설가의 10~20%
    if any(a.installed_year is None for a in farm.assets):
        disc_min += fac_total * 0.10
        disc_max += fac_total * 0.20

    # ② 경제수령 초과 → 토지가의 0~5%
    eco_life = _ECONOMIC_LIFE.get(farm.crop_code, 20)
    if farm.tree_age > eco_life:
        disc_max += land_val.point * 0.05  # disc_min += 0 (보수적 최소 0%)

    raw_value_min = land_val.min + fac_min + gw_min - disc_max
    raw_value_max = land_val.max + fac_max + gw_max - disc_min

    # 하한 클리핑: value_min ≥ land_min
    value_min = max(raw_value_min, land_val.min)
    value_max = max(raw_value_max, land_val.min)

    return ValuationResult(
        est_income_min=income_res.min,
        est_income_max=income_res.max,
        est_value_min=value_min,
        est_value_max=value_max,
        confidence_grade=grade,
        income_point=income_res.point,
        land_value_point=land_val.point,
        facility_value=fac_total,
        goodwill_min=gw_min,
        goodwill_max=gw_max,
        income_adjustment=income_res.adjustment,
        revenue_cap_applied=income_res.cap_applied,
    )


def calc_match_score(
    young: YoungFarmerInput, farm: FarmProfileForMatch
) -> MatchResult:
    """매칭 점수 (formula.md §7). 만점 100, 하한 0.

    양방향 사용: 농가 화면(후보 추천)·청년농 화면(농장 추천) 동일 점수.
    """
    region_score = 20.0 if (young.pref_sido is None or young.pref_sido == farm.sido) else 0.0
    # TODO 7월: 인접 도 부분점수(10점) — RAG 기반 행정구역 인접성

    crop_score = 20.0 if (young.pref_crop is None or young.pref_crop == farm.crop_code) else 0.0

    capital_ratio = _clamp(
        young.available_capital / farm.est_value_min if farm.est_value_min > 0 else 0.0,
        0.0, 1.0,
    )
    capital_score = 20.0 * capital_ratio

    experience_score = 15.0 * _clamp(young.experience_years / 5.0, 0.0, 1.0)

    if young.pref_succession == farm.succession_type:
        succession_score = 15.0
    else:
        succession_score = _SUCCESSION_COMPAT.get(
            (young.pref_succession, farm.succession_type), 0.0
        )

    if young.policy_fund and farm.est_value_min <= POLICY_FUND_LIMIT:
        policy_score = 10.0
    elif young.policy_fund:
        policy_score = 5.0
    else:
        policy_score = 0.0

    risk_penalty = 0.0
    if young.available_capital < farm.est_value_min * 0.5:
        risk_penalty += 10.0
    if farm.crop_difficulty_high and young.experience_years == 0:
        risk_penalty += 5.0

    total = max(
        0.0,
        region_score + crop_score + capital_score + experience_score
        + succession_score + policy_score - risk_penalty,
    )

    return MatchResult(
        total_score=total,
        region_score=region_score,
        crop_score=crop_score,
        capital_score=capital_score,
        experience_score=experience_score,
        succession_score=succession_score,
        policy_score=policy_score,
        risk_penalty=risk_penalty,
    )
