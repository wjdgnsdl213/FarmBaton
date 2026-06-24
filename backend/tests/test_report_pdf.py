"""PDF 표현 컨텍스트(_build_report_context) 검증.

핵심 원칙: 표현 레이어는 calc_total_value의 결정론 산출값을 포맷만 입혀야
하며, 화면에 표시되는 금액이 원본 계산값(만원 반올림)과 정확히 일치해야 한다.
"""
from backend.app.routers.farms import _build_report_context
from backend.app.services.report_ai import _fallback_narrative, ReportContext
from backend.app.services.valuation import (
    AssetData, FarmInput, LandData,
    calc_total_value, derive_risk_flags, grade_reasons,
)

YEAR = 2026


def _make_input(*, deal, deal_cnt, installed):
    return FarmInput(
        crop_code="APPLE", tree_age=10, area_m2=5000.0,
        income_10a=4_000_000, age_coef=1.0, trend_index=0.93,
        land=LandData(area_m2=5000.0, official_price_m2=120_000,
                      deal_price_m2=deal, deal_sample_cnt=deal_cnt),
        assets=[AssetData("COLD_STORAGE_SMALL", 60, installed, "B", 900_000, 15, 0.1)],
    )


def _ctx_for(fi, audience="YOUNG"):
    result = calc_total_value(fi, YEAR)
    flags = derive_risk_flags(fi)
    reasons = grade_reasons(fi)
    nr = _fallback_narrative(ReportContext(
        crop_code=fi.crop_code, tree_age=fi.tree_age, area_m2=fi.area_m2, sido="충북",
        confidence_grade=result.confidence_grade,
        est_income_min=round(result.est_income_min/10000), est_income_max=round(result.est_income_max/10000),
        est_value_min=round(result.est_value_min/10000), est_value_max=round(result.est_value_max/10000),
        land_value_point=round(result.land_value_point/10000), facility_value=round(result.facility_value/10000),
        goodwill_min=round(result.goodwill_min/10000), goodwill_max=round(result.goodwill_max/10000),
        risk_flags=flags, audience=audience,
    ))
    ctx = _build_report_context(
        farm_input=fi, result=result, risk_flags=flags, reasons=reasons,
        normal_year_text="참고", ai_summary=nr.summary, ai_risk_notes=nr.risk_notes,
        ai_advice_items=nr.advice_items, audience=audience,
        address="충청북도 충주시 가주동 483", sido="충북", succession_type="SALE",
    )
    return result, ctx


def test_displayed_amounts_match_calculation():
    """히어로·시나리오 금액이 원본 계산값(만원 반올림)과 정확히 일치."""
    fi = _make_input(deal=130_000, deal_cnt=5, installed=2017)
    result, ctx = _ctx_for(fi)

    v_min = round(result.est_value_min / 10000)
    v_max = round(result.est_value_max / 10000)
    i_min = round(result.est_income_min / 10000)
    i_max = round(result.est_income_max / 10000)

    # 히어로 만원 보조 표기 = 계산값 그대로
    assert f"{v_min:,}만원 ~ {v_max:,}만원" == ctx["value_manwon"]
    assert f"{i_min:,} ~ {i_max:,}만원" == ctx["income_range"]
    # 억 단위 = 만원/10000
    assert ctx["value_eok"] == f"{v_min/10000:.2f}억 ~ {v_max/10000:.2f}억원"
    # 시나리오 하한/상한이 히어로와 동일 숫자
    assert ctx["scenarios"][0]["value"] == f"{v_min:,}만원"
    assert ctx["scenarios"][2]["value"] == f"{v_max:,}만원"


def test_small_amount_shown_in_manwon():
    """1억 미만 인수 검토가는 억이 아니라 만원으로 표기 (소면적 농장)."""
    fi = FarmInput(
        crop_code="APPLE", tree_age=8, area_m2=1500.0,
        income_10a=4_000_000, age_coef=1.0, trend_index=0.93,
        land=LandData(area_m2=1500.0, official_price_m2=60_000,
                      deal_price_m2=65_000, deal_sample_cnt=4),
        assets=[],
    )
    result, ctx = _ctx_for(fi)
    v_max = round(result.est_value_min / 10000), round(result.est_value_max / 10000)
    # 둘 다 1억 미만이면 억 표기가 없어야 함
    if result.est_value_max < 100_000_000:
        assert "억" not in ctx["value_eok"]
        assert "만원" in ctx["value_eok"]
        assert ctx["value_manwon"] == ""  # 보조 만원 줄은 비움(중복 방지)


def test_grade_c_when_data_sufficient():
    fi = _make_input(deal=130_000, deal_cnt=5, installed=2017)
    result, ctx = _ctx_for(fi)
    assert ctx["confidence_grade"] == "C"
    assert ctx["grade_downgrades"] == []


def test_grade_downgrades_surface_reasons_and_missing():
    """실거래 없음 + 시설연도 미상 → D등급 + 하향 사유·누락 데이터 노출."""
    fi = _make_input(deal=None, deal_cnt=0, installed=None)
    result, ctx = _ctx_for(fi)
    assert ctx["confidence_grade"] == "D"
    assert len(ctx["grade_downgrades"]) == 2
    assert any("실거래" in m for m in ctx["grade_missing"])
    assert any("설치연도" in m for m in ctx["grade_missing"])


def test_risk_categories_present():
    fi = _make_input(deal=None, deal_cnt=0, installed=None)
    _, ctx = _ctx_for(fi)
    # 현장 확인 항목은 항상 고정 제공
    assert len(ctx["risk_onsite"]) >= 3
    # 정보 부족(하향 사유)이 채워짐
    assert len(ctx["risk_missing"]) == 2
