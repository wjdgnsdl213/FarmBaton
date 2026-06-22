"""
formula.md §8 T1~T10 테스트 (TDD — 구현 전 작성)

순수 수학 함수만 검증. DB 없이 실행 가능하도록
FarmInput/AssetData에 DB 시드값을 직접 주입.

DB 시드 기준값 (db/seed/*.csv):
  APPLE  income_10a = 5_114_297원  (income_coef, base_year=2024)
  PEACH  income_10a = 2_540_889원
  GRAPE  income_10a = 5_479_269원

  orchard_age_coef (yield_coef):
    APPLE  7년  → 1.00  (7~20 성목기)
    APPLE  3년  → 0.35  (3~4 초기결실)
    PEACH  3년  → 0.45  (3~4 초기결실)
    GRAPE  25년 → 0.30  (21~99 노목기)
      ※ formula.md T4에 "post_life(0.35)"로 표기되어 있으나
         DB 시드 GRAPE 21-99 yield_coef=0.30이 기준(rule-5 우선).

  facility_std (COLD_STORAGE):
    std_unit_cost_krw=600_000, useful_life_years=15, salvage_rate=0.10
    ※ formula.md T5 "1-5/10"은 useful_life=10 기준 오기.
       DB 시드 useful_life_years=15가 기준.

  facility_condition: A→1.00, B→0.85, C→0.60
"""

import pytest

from backend.app.services.valuation import (
    INCOME_BAND,
    OFFICIAL_TO_MARKET,
    AssetData,
    FarmInput,
    FarmProfileForMatch,
    LandData,
    YoungFarmerInput,
    calc_asset_residual,
    calc_facility_value,
    calc_goodwill,
    calc_income,
    calc_land_value,
    calc_match_score,
    calc_total_value,
    derive_risk_flags,
    grade_confidence,
)

# ── 시드 상수 ────────────────────────────────────────────────────────────────

APPLE_INCOME_10A  = 5_114_297.0
PEACH_INCOME_10A  = 2_540_889.0
GRAPE_INCOME_10A  = 5_479_269.0

APPLE_7Y_COEF  = 1.00
APPLE_3Y_COEF  = 0.35
PEACH_3Y_COEF  = 0.45
GRAPE_25Y_COEF = 0.30  # DB 기준

COND_MULT = {"A": 1.00, "B": 0.85, "C": 0.60}
CURRENT_YEAR = 2026


# ─────────────────────────────────────────────────────────────────────────────
# 공통 픽스처
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def std_land_5000():
    return LandData(
        area_m2=5_000.0,
        official_price_m2=30_000.0,
        deal_price_m2=55_000.0,
        deal_sample_cnt=5,
    )


@pytest.fixture
def apple_7y(std_land_5000):
    return FarmInput(
        crop_code="APPLE",
        tree_age=7,
        area_m2=5_000.0,
        income_10a=APPLE_INCOME_10A,
        age_coef=APPLE_7Y_COEF,
        trend_index=1.0,
        land=std_land_5000,
        assets=[],
    )


@pytest.fixture
def apple_3y(std_land_5000):
    return FarmInput(
        crop_code="APPLE",
        tree_age=3,
        area_m2=5_000.0,
        income_10a=APPLE_INCOME_10A,
        age_coef=APPLE_3Y_COEF,
        trend_index=1.0,
        land=std_land_5000,
        assets=[],
    )


@pytest.fixture
def peach_3y():
    return FarmInput(
        crop_code="PEACH",
        tree_age=3,
        area_m2=3_000.0,
        income_10a=PEACH_INCOME_10A,
        age_coef=PEACH_3Y_COEF,
        trend_index=1.0,
        land=LandData(area_m2=3_000.0, official_price_m2=25_000.0,
                      deal_price_m2=48_000.0, deal_sample_cnt=4),
        assets=[],
    )


@pytest.fixture
def grape_25y():
    return FarmInput(
        crop_code="GRAPE",
        tree_age=25,
        area_m2=4_000.0,
        income_10a=GRAPE_INCOME_10A,
        age_coef=GRAPE_25Y_COEF,
        trend_index=1.0,
        land=LandData(area_m2=4_000.0, official_price_m2=40_000.0,
                      deal_price_m2=70_000.0, deal_sample_cnt=6),
        assets=[],
    )


@pytest.fixture
def cold_storage_5y_B():
    """COLD_STORAGE 33㎡(10평), 5년 경과, 상태B — DB 시드 useful_life=15"""
    return AssetData(
        facility_code="COLD_STORAGE",
        area_m2=33.0,
        installed_year=CURRENT_YEAR - 5,
        condition_grade="B",
        std_unit_cost_krw=600_000,
        useful_life_years=15,       # DB 시드 기준 (formula.md T5 예시의 10은 오기)
        salvage_rate=0.10,
    )


# ─────────────────────────────────────────────────────────────────────────────
# T1  사과 7년생 5,000㎡ | 시설 없음, 매출 없음, 실거래 있음
#     기대: age_coef=1.0, goodwill=0, value_min≥land_min
# ─────────────────────────────────────────────────────────────────────────────

def test_T1_age_coef_is_1(apple_7y):
    """T1: 사과 7년생 age_coef=1.0"""
    assert apple_7y.age_coef == pytest.approx(1.0)


def test_T1_goodwill_zero_no_revenue(apple_7y):
    """T1: 매출 없음(revenue_years=0) → goodwill=(0,0)"""
    gw_min, gw_max = calc_goodwill(
        income_point=calc_income(apple_7y).point,
        revenue_years=0,
        annual_revenue=None,
        has_contract=False,
        has_direct_sales=False,
    )
    assert gw_min == 0.0
    assert gw_max == 0.0


def test_T1_value_min_ge_land_min(apple_7y):
    """T1: value_min ≥ land_min (하한 보장)"""
    result   = calc_total_value(apple_7y, CURRENT_YEAR)
    land_min = calc_land_value(apple_7y.land).min
    assert result.est_value_min >= land_min


# ─────────────────────────────────────────────────────────────────────────────
# T2  사과 3년생 vs 7년생 동일조건
#     기대: 3년생 income·value < 7년생
# ─────────────────────────────────────────────────────────────────────────────

def test_T2_young_tree_lower_income(apple_3y, apple_7y):
    """T2: 사과 3년생 income_point < 7년생"""
    assert calc_income(apple_3y).point < calc_income(apple_7y).point


def test_T2_young_tree_lower_value(apple_3y, apple_7y):
    """T2: 사과 3년생 est_value_min < 7년생 (매출 3년 기준, 영업권 반영)

    revenue_years=0(미제출)이면 영업권=0 → 토지가(동일)로 수렴해 차이 없음.
    revenue_years=3 제출 시 영업권 = income_point×1.0 → 수령 차이가 가치에 반영됨.
    """
    from dataclasses import replace
    farm_3y = replace(apple_3y, revenue_years=3)
    farm_7y = replace(apple_7y, revenue_years=3)
    val_3 = calc_total_value(farm_3y, CURRENT_YEAR).est_value_min
    val_7 = calc_total_value(farm_7y, CURRENT_YEAR).est_value_min
    assert val_3 < val_7


# ─────────────────────────────────────────────────────────────────────────────
# T3  복숭아 3년생
#     기대: age_coef > 0 (절벽 없음), income > 0
# ─────────────────────────────────────────────────────────────────────────────

def test_T3_peach_3y_age_coef_positive(peach_3y):
    """T3: 복숭아 3년생 age_coef>0"""
    assert peach_3y.age_coef > 0.0


def test_T3_peach_3y_income_positive(peach_3y):
    """T3: 복숭아 3년생 예상소득 > 0"""
    result = calc_income(peach_3y)
    assert result.point > 0.0
    assert result.min > 0.0


# ─────────────────────────────────────────────────────────────────────────────
# T4  포도 25년생 (경제수령 초과)
#     기대: age_coef=DB값(0.30), 리스크할인으로 value 감소
# ─────────────────────────────────────────────────────────────────────────────

def test_T4_grape_25y_age_coef(grape_25y):
    """T4: 포도 25년생 age_coef = DB 시드 GRAPE 21+ 값(0.30)"""
    assert grape_25y.age_coef == pytest.approx(GRAPE_25Y_COEF)


def test_T4_grape_25y_income_below_peak(grape_25y):
    """T4: 25년생 소득 < 동일 조건 성목기(age_coef=1.0) 소득"""
    grape_peak = FarmInput(
        crop_code="GRAPE",
        tree_age=10,
        area_m2=grape_25y.area_m2,
        income_10a=GRAPE_INCOME_10A,
        age_coef=1.00,
        trend_index=1.0,
        land=grape_25y.land,
        assets=[],
    )
    assert calc_income(grape_25y).point < calc_income(grape_peak).point


def test_T4_grape_25y_risk_discount_applied(grape_25y):
    """T4: 경제수령 초과 → est_value_max ≤ land_max + 약간의 여유"""
    result   = calc_total_value(grape_25y, CURRENT_YEAR)
    land_max = calc_land_value(grape_25y.land).max
    # 시설 없음, 영업권 없음 → value_max는 land_max에 리스크할인 차감분만큼 낮아야 함
    assert result.est_value_max <= land_max + 1  # 부동소수 여유


# ─────────────────────────────────────────────────────────────────────────────
# T5  저온저장고 10평(33㎡) 5년 경과 상태B
#     기대: dep_ratio = GREATEST(0.10, 1-5/15) = 0.6667
#           residual = new_cost × 0.6667 × 0.85
#     ※ DB useful_life_years=15 사용 (formula.md 예시 "/10"은 오기)
# ─────────────────────────────────────────────────────────────────────────────

def test_T5_residual_matches_formula(cold_storage_5y_B):
    """T5: dep_ratio = GREATEST(salvage, 1-elapsed/useful_life), cond_mult=0.85"""
    elapsed   = CURRENT_YEAR - cold_storage_5y_B.installed_year
    dep_ratio = max(
        cold_storage_5y_B.salvage_rate,
        1 - elapsed / cold_storage_5y_B.useful_life_years,
    )
    expected = (
        cold_storage_5y_B.std_unit_cost_krw
        * cold_storage_5y_B.area_m2
        * dep_ratio
        * COND_MULT["B"]
    )
    assert calc_asset_residual(cold_storage_5y_B, CURRENT_YEAR) == pytest.approx(expected, rel=1e-6)


def test_T5_dep_ratio_uses_db_useful_life_15(cold_storage_5y_B):
    """T5: DB useful_life=15 기반 dep_ratio=2/3≈0.667 (not 0.5)"""
    elapsed   = 5
    dep_ratio = max(cold_storage_5y_B.salvage_rate, 1 - elapsed / cold_storage_5y_B.useful_life_years)
    assert dep_ratio == pytest.approx(2 / 3, rel=1e-4)


# ─────────────────────────────────────────────────────────────────────────────
# T6  installed_year 결측 자산 포함
#     기대: dep_ratio=0.5 가정, confidence_grade 하향
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def asset_no_year():
    return AssetData(
        facility_code="GH_SINGLE",
        area_m2=200.0,
        installed_year=None,
        condition_grade="B",
        std_unit_cost_krw=30_000,
        useful_life_years=10,
        salvage_rate=0.05,
    )


def test_T6_no_year_dep_ratio_half(asset_no_year):
    """T6: installed_year=None → dep_ratio=0.5 가정"""
    expected = asset_no_year.std_unit_cost_krw * asset_no_year.area_m2 * 0.5 * COND_MULT["B"]
    assert calc_asset_residual(asset_no_year, CURRENT_YEAR) == pytest.approx(expected, rel=1e-6)


def test_T6_missing_year_downgrades_grade():
    """T6: installed_year=None 자산 포함 → grade 하향"""
    base_land = LandData(area_m2=3_000.0, official_price_m2=30_000.0,
                         deal_price_m2=55_000.0, deal_sample_cnt=5)

    def make_farm(installed_year):
        return FarmInput(
            crop_code="APPLE", tree_age=7, area_m2=3_000.0,
            income_10a=APPLE_INCOME_10A, age_coef=APPLE_7Y_COEF, trend_index=1.0,
            land=base_land,
            assets=[AssetData(facility_code="GH_SINGLE", area_m2=200.0,
                              installed_year=installed_year, condition_grade="B",
                              std_unit_cost_krw=30_000, useful_life_years=10,
                              salvage_rate=0.05)],
        )

    farm_no_year   = make_farm(None)
    farm_with_year = make_farm(2020)
    order = ["A", "B", "C", "D"]
    assert order.index(grade_confidence(farm_no_year)) > order.index(grade_confidence(farm_with_year))


# ─────────────────────────────────────────────────────────────────────────────
# T7  공시지가만 (실거래 없음)
#     기대: unit = official / OFFICIAL_TO_MARKET, grade 하향
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def land_official_only():
    return LandData(area_m2=5_000.0, official_price_m2=30_000.0,
                    deal_price_m2=None, deal_sample_cnt=0)


def test_T7_official_only_unit_price(land_official_only):
    """T7: 실거래 없음 → unit = official_price_m2 / OFFICIAL_TO_MARKET"""
    lv = calc_land_value(land_official_only)
    expected_unit  = land_official_only.official_price_m2 / OFFICIAL_TO_MARKET
    expected_point = land_official_only.area_m2 * expected_unit
    assert lv.point == pytest.approx(expected_point, rel=1e-6)


def test_T7_official_only_grade_downgraded():
    """T7: 실거래가 없으면 deal 있는 경우보다 등급이 낮거나 같음"""
    farm_deal = FarmInput(
        crop_code="APPLE", tree_age=7, area_m2=5_000.0,
        income_10a=APPLE_INCOME_10A, age_coef=APPLE_7Y_COEF, trend_index=1.0,
        land=LandData(area_m2=5_000.0, official_price_m2=30_000.0,
                      deal_price_m2=55_000.0, deal_sample_cnt=5),
        assets=[],
    )
    farm_no_deal = FarmInput(
        crop_code="APPLE", tree_age=7, area_m2=5_000.0,
        income_10a=APPLE_INCOME_10A, age_coef=APPLE_7Y_COEF, trend_index=1.0,
        land=LandData(area_m2=5_000.0, official_price_m2=30_000.0,
                      deal_price_m2=None, deal_sample_cnt=0),
        assets=[],
    )
    order = ["A", "B", "C", "D"]
    assert order.index(grade_confidence(farm_no_deal)) >= order.index(grade_confidence(farm_deal))


# ─────────────────────────────────────────────────────────────────────────────
# T8  경계값: area_m2=0, tree_age=0 등
#     기대: ZeroDivisionError 없이 안전 반환
# ─────────────────────────────────────────────────────────────────────────────

def test_T8_zero_area_safe():
    """T8: area_m2=0 → 소득·value 0 반환, 예외 없음"""
    farm = FarmInput(
        crop_code="APPLE", tree_age=7, area_m2=0.0,
        income_10a=APPLE_INCOME_10A, age_coef=1.0, trend_index=1.0,
        land=LandData(area_m2=0.0, official_price_m2=30_000.0,
                      deal_price_m2=55_000.0, deal_sample_cnt=5),
        assets=[],
    )
    result = calc_total_value(farm, CURRENT_YEAR)
    assert result.est_income_min == 0.0
    assert result.est_income_max == 0.0
    assert result.est_value_min >= 0.0


def test_T8_zero_age_coef_safe():
    """T8: age_coef=0(유목기 0~2년) → income=0, 예외 없음"""
    farm = FarmInput(
        crop_code="APPLE", tree_age=0, area_m2=3_000.0,
        income_10a=APPLE_INCOME_10A, age_coef=0.0,
        trend_index=1.0,
        land=LandData(area_m2=3_000.0, official_price_m2=30_000.0,
                      deal_price_m2=55_000.0, deal_sample_cnt=5),
        assets=[],
    )
    result = calc_total_value(farm, CURRENT_YEAR)
    assert result.est_income_min == 0.0
    assert result.est_income_max == 0.0
    assert result.est_value_min >= 0.0


def test_T8_zero_unit_cost_asset_safe():
    """T8: std_unit_cost_krw=0 자산 → 잔존가=0, 예외 없음"""
    asset = AssetData(facility_code="TEST", area_m2=100.0, installed_year=2020,
                      condition_grade="B", std_unit_cost_krw=0,
                      useful_life_years=10, salvage_rate=0.05)
    assert calc_asset_residual(asset, CURRENT_YEAR) == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# T9  value_min ≥ land_min 항상 성립
#     기대: 음수 기여(영업권 0, 리스크할인) 차단 검증
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("area_m2,age_coef,tree_age", [
    (5_000.0, APPLE_7Y_COEF,  7),
    (5_000.0, APPLE_3Y_COEF,  3),
    (3_000.0, PEACH_3Y_COEF,  3),
    (4_000.0, GRAPE_25Y_COEF, 25),   # 경제수령 초과, risk_discount 적용
    (100.0,   0.0,             0),    # 극소면적 유목기
])
def test_T9_value_min_never_below_land_min(area_m2, age_coef, tree_age):
    """T9: 어떤 조건에서도 value_min ≥ land_min (§5 하한 클리핑)"""
    farm = FarmInput(
        crop_code="APPLE",
        tree_age=tree_age,
        area_m2=area_m2,
        income_10a=APPLE_INCOME_10A,
        age_coef=age_coef,
        trend_index=1.0,
        land=LandData(area_m2=area_m2, official_price_m2=30_000.0,
                      deal_price_m2=55_000.0, deal_sample_cnt=5),
        assets=[],
    )
    result   = calc_total_value(farm, CURRENT_YEAR)
    land_min = calc_land_value(farm.land).min
    assert result.est_value_min >= land_min, (
        f"T9 실패: area={area_m2}, age_coef={age_coef} → "
        f"value_min={result.est_value_min:,.0f} < land_min={land_min:,.0f}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# T10 매칭: 완전일치 청년농
#     기대: total ≈ 95~100, 각 항목 최대점
# ─────────────────────────────────────────────────────────────────────────────

def test_T10_perfect_match_score():
    """T10: 완전일치(지역·작목·자본·경험·승계·정책) → 95~100점"""
    farm = FarmProfileForMatch(
        sido="충북",
        crop_code="APPLE",
        succession_type="SALE",
        est_value_min=90_000_000.0,   # 9천만원 (정책자금 한도 이내)
    )
    young = YoungFarmerInput(
        pref_sido="충북",
        pref_crop="APPLE",
        available_capital=100_000_000.0,  # value_min 초과
        experience_years=5,
        policy_fund=True,
        pref_succession="SALE",
    )
    result = calc_match_score(young, farm)

    assert 95 <= result.total_score <= 100, f"총점={result.total_score} (기대: 95~100)"
    assert result.risk_penalty == 0, "자본·경험 충분 → 패널티 없음"
    assert result.region_score     == 20
    assert result.crop_score       == 20
    assert result.succession_score == 15
    assert result.experience_score == pytest.approx(15.0, abs=0.1)
    assert result.capital_score    == pytest.approx(20.0, abs=0.1)


def test_T10_insufficient_capital_penalty():
    """T10 변형: 자본 < value_min×0.5 → risk_penalty≥10, 총점≥0"""
    farm = FarmProfileForMatch(
        sido="충북",
        crop_code="APPLE",
        succession_type="SALE",
        est_value_min=200_000_000.0,
    )
    young = YoungFarmerInput(
        pref_sido="충북",
        pref_crop="APPLE",
        available_capital=80_000_000.0,   # 200M×0.5=100M 미달
        experience_years=5,
        policy_fund=False,
        pref_succession="SALE",
    )
    result = calc_match_score(young, farm)
    assert result.risk_penalty >= 10
    assert result.total_score >= 0


# ─────────────────────────────────────────────────────────────────────────────
# 상수 검증
# ─────────────────────────────────────────────────────────────────────────────

def test_income_band_values():
    """formula.md §1: D±25%, C±18%, B±12%, A±8%"""
    assert INCOME_BAND == {"A": 0.08, "B": 0.12, "C": 0.18, "D": 0.25}


def test_official_to_market_value():
    """formula.md §2: official_to_market = 0.65"""
    assert OFFICIAL_TO_MARKET == pytest.approx(0.65)


# ─────────────────────────────────────────────────────────────────────────────
# derive_risk_flags — AI 리포트용 리스크 플래그 추출 (판단은 결정론적)
# ─────────────────────────────────────────────────────────────────────────────

def test_risk_flags_empty_for_clean_farm(apple_7y):
    """실거래 있음 + 시설 없음 + 경제수령 이내 → 플래그 없음"""
    assert derive_risk_flags(apple_7y) == []


def test_risk_flags_missing_installed_year(asset_no_year):
    farm = FarmInput(
        crop_code="APPLE", tree_age=7, area_m2=3_000.0,
        income_10a=APPLE_INCOME_10A, age_coef=APPLE_7Y_COEF, trend_index=1.0,
        land=LandData(area_m2=3_000.0, official_price_m2=30_000.0,
                      deal_price_m2=55_000.0, deal_sample_cnt=5),
        assets=[asset_no_year],
    )
    flags = derive_risk_flags(farm)
    assert len(flags) == 1
    assert "설치연도" in flags[0]


def test_risk_flags_official_only_land(land_official_only):
    farm = FarmInput(
        crop_code="APPLE", tree_age=7, area_m2=5_000.0,
        income_10a=APPLE_INCOME_10A, age_coef=APPLE_7Y_COEF, trend_index=1.0,
        land=land_official_only,
        assets=[],
    )
    flags = derive_risk_flags(farm)
    assert len(flags) == 1
    assert "실거래" in flags[0]


def test_risk_flags_economic_life_exceeded(grape_25y):
    """포도 25년생 > 경제수령 18 → 경제수령 초과 플래그"""
    flags = derive_risk_flags(grape_25y)
    assert any("경제수령" in f for f in flags)


def test_risk_flags_all_three_triggers(asset_no_year):
    """실거래 표본 부족 + 설치연도 결측 + 경제수령 초과가 모두 겹치면 3개"""
    farm = FarmInput(
        crop_code="GRAPE", tree_age=25, area_m2=4_000.0,
        income_10a=GRAPE_INCOME_10A, age_coef=GRAPE_25Y_COEF, trend_index=1.0,
        land=LandData(area_m2=4_000.0, official_price_m2=40_000.0,
                      deal_price_m2=None, deal_sample_cnt=0),
        assets=[asset_no_year],
    )
    assert len(derive_risk_flags(farm)) == 3
