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
    # 영업권 입력 (선택)
    annual_revenue: Optional[float] = None
    revenue_years: int = 0         # 0: 미제출, 1: 1년, 3: 3년
    has_contract: bool = False
    has_direct_sales: bool = False


@dataclass
class YoungFarmerInput:
    """매칭 청년농 입력."""
    pref_sido: str
    pref_crop: str
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

    MVP 기본 'C'에서 시작. 하향 트리거 1건당 1단계 down, 최저 D.
    - 실거래 부실 (공시지가만 OR 표본<3): 한 단계 down
    - installed_year 결측 자산 존재: 한 단계 down
    """
    _GRADES = ["A", "B", "C", "D"]
    idx = 2  # C

    if farm.land.deal_price_m2 is None or (farm.land.deal_sample_cnt or 0) < 3:
        idx += 1

    if any(a.installed_year is None for a in farm.assets):
        idx += 1

    return _GRADES[min(idx, 3)]


def calc_income(farm: FarmInput) -> IncomeResult:
    """예상 연소득 점추정·범위 (formula.md §1).

    area_m2=0 또는 age_coef=0 이면 0 반환 (ZeroDivision 없음).
    """
    if farm.area_m2 == 0 or farm.age_coef == 0:
        return IncomeResult(point=0.0, min=0.0, max=0.0)

    base_income = farm.income_10a * (farm.area_m2 / 1_000.0)

    if farm.annual_revenue is not None and base_income > 0:
        skill_adj = _clamp(farm.annual_revenue / base_income, 0.7, 1.3)
    else:
        skill_adj = 1.0

    point = base_income * farm.age_coef * farm.trend_index * skill_adj

    band = INCOME_BAND[grade_confidence(farm)]
    return IncomeResult(
        point=point,
        min=point * (1.0 - band),
        max=point * (1.0 + band),
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
    )


def calc_match_score(
    young: YoungFarmerInput, farm: FarmProfileForMatch
) -> MatchResult:
    """매칭 점수 (formula.md §7). 만점 100, 하한 0.

    양방향 사용: 농가 화면(후보 추천)·청년농 화면(농장 추천) 동일 점수.
    """
    region_score = 20.0 if young.pref_sido == farm.sido else 0.0
    # TODO 7월: 인접 도 부분점수(10점) — RAG 기반 행정구역 인접성

    crop_score = 20.0 if young.pref_crop == farm.crop_code else 0.0

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
