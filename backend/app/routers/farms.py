"""
농가 등록 · 인수 검토 리포트 라우터.

POST /api/farms           — 농가 등록 + 자동 가치평가 (P2 핵심 플로우)
GET  /api/farms/{id}      — 농장 상세
GET  /api/farms/{id}/valuation — 저장된 가치평가 조회 또는 재산출
"""
from __future__ import annotations

import datetime
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.app.db import get_db
from backend.app.schemas import (
    DISCLAIMER,
    AssetCreate,
    AssetSummary,
    ConsultRequestCreate,
    ConsultRequestResponse,
    FarmCreate,
    FarmCreateResponse,
    FarmDetail,
    ValuationResponse,
)
from backend.app.services.db_loader import load_farm_input
from backend.app.services.pdf_render import render_report_pdf
from backend.app.services.report_ai import CROP_NAMES, GRADE_DESC, ReportContext, generate_narrative
from backend.app.services.valuation import calc_total_value, derive_risk_flags

router = APIRouter(prefix="/api/farms", tags=["farms"])

CURRENT_YEAR = datetime.date.today().year

SUCC_NAMES = {"SALE": "매도", "LEASE": "임대", "JOINT": "공동경영", "MENTORING": "멘토후독립"}


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _to_만원(value: float) -> int:
    """원 → 만원 반올림."""
    return round(value / 10_000)


def _build_valuation_response(farm_id: int, result) -> ValuationResponse:
    return ValuationResponse(
        farm_id=farm_id,
        confidence_grade=result.confidence_grade,
        est_income_min=_to_만원(result.est_income_min),
        est_income_max=_to_만원(result.est_income_max),
        est_value_min=_to_만원(result.est_value_min),
        est_value_max=_to_만원(result.est_value_max),
        income_point=_to_만원(result.income_point),
        land_value_point=_to_만원(result.land_value_point),
        facility_value=_to_만원(result.facility_value),
        goodwill_min=_to_만원(result.goodwill_min),
        goodwill_max=_to_만원(result.goodwill_max),
    )


def _cache_valuation(farm_id: int, result, conn) -> None:
    """farm 테이블에 평가 결과 캐시."""
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE farm
            SET est_value_min    = %s,
                est_value_max    = %s,
                est_income_min   = %s,
                est_income_max   = %s,
                confidence_grade = %s::confidence_t,
                updated_at       = now()
            WHERE id = %s
        """, (
            result.est_value_min,
            result.est_value_max,
            result.est_income_min,
            result.est_income_max,
            result.confidence_grade,
            farm_id,
        ))
    conn.commit()


def _insert_farm(data: FarmCreate, parcel_id: Optional[int],
                 bjd_cd: Optional[str], area_m2: float,
                 sido: Optional[str], sigungu: Optional[str], conn) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO farm (
                address, sido, sigungu, bjd_cd, area_m2, crop_code,
                tree_age, succession_type, timing, annual_revenue,
                sales_channel, parcel_id, status, is_demo
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s)
            RETURNING id
        """, (
            data.address,
            sido or _extract_sido(data.address),
            sigungu,
            bjd_cd,
            area_m2,
            data.crop_code,
            data.tree_age,
            data.succession_type,
            data.timing,
            data.annual_revenue,
            data.sales_channel,
            parcel_id,
            data.is_demo,
        ))
        farm_id = cur.fetchone()[0]
    return farm_id


def _insert_assets(farm_id: int, assets: list[AssetCreate], conn) -> None:
    if not assets:
        return
    with conn.cursor() as cur:
        for a in assets:
            cur.execute("""
                INSERT INTO farm_asset (farm_id, facility_code, area_m2, installed_year, condition_grade)
                VALUES (%s, %s, %s, %s, %s)
            """, (farm_id, a.facility_code, a.area_m2, a.installed_year, a.condition_grade))


def _extract_sido(address: str) -> str:
    """주소 첫 토큰에서 시도 추출 (폴백)."""
    mapping = {"충북": "충북", "충청북도": "충북",
                "경북": "경북", "경상북도": "경북",
                "충남": "충남", "충청남도": "충남"}
    for k, v in mapping.items():
        if k in address:
            return v
    return address.split()[0] if address else ""


KNN_DISTANCE_WARN_KM = 20.0  # 이 거리를 넘는 KNN 매칭은 매칭 실패로 취급(하드 컷오프)


def _call_farm_card(lon: float, lat: float, crop_code: str, address_sido: str | None, conn):
    """필지 매칭: ST_Contains 우선, 없으면 같은 시도 내 KNN, 최후엔 전역 KNN.

    Returns (parcel_id, sido, sigungu, bjd_cd, area_m2) or None.
    마을 중심좌표는 개별 필지 안에 들어오지 않는 경우가 많아 KNN 폴백 필수.
    시도 스코프 없이 전역 KNN만 쓰면 주소 오인식 시 수십km 떨어진 엉뚱한
    필지가 붙을 수 있어(검증 중 서울 좌표 → 67km 거리 천안시 필지 매칭
    확인), 같은 시도로 먼저 좁히고 거리 임계값을 넘으면 매칭 실패(None)로
    처리한다 — 틀린 값을 자신있게 보여주는 것보다 "필지 못 찾음 → 면적
    직접 입력 + 시도 단위 폴백"(db_loader._load_land)으로 넘기는 쪽이 안전.
    """
    try:
        with conn.cursor() as cur:
            # 1차: ST_Contains (정확 포함)
            cur.execute(
                "SELECT parcel_id, sido, sigungu, bjd_cd, area_m2 "
                "FROM fn_farm_card(%s, %s, %s::crop_code_t)",
                (lon, lat, crop_code),
            )
            row = cur.fetchone()
            if row:
                return row

            # 2차: 같은 시도 내 KNN (스코프를 좁혀 오매칭 방지)
            row = None
            if address_sido:
                cur.execute("""
                    SELECT p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2,
                           ST_Distance(
                               p.geom::geography,
                               ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                           ) / 1000.0 AS dist_km
                    FROM parcel p
                    WHERE p.sido = %s
                    ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    LIMIT 1
                """, (lon, lat, address_sido, lon, lat))
                row = cur.fetchone()

            # 3차: 전역 KNN (시도 추정조차 안 된 경우의 최후 폴백)
            if not row:
                cur.execute("""
                    SELECT p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2,
                           ST_Distance(
                               p.geom::geography,
                               ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography
                           ) / 1000.0 AS dist_km
                    FROM parcel p
                    ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                    LIMIT 1
                """, (lon, lat, lon, lat))
                row = cur.fetchone()

            if not row:
                return None

            parcel_id, sido, sigungu, bjd_cd, area_m2, dist_km = row
            if dist_km is not None and dist_km > KNN_DISTANCE_WARN_KM:
                return None  # 너무 멀면 매칭 실패로 취급 (하드 컷오프)
            return (parcel_id, sido, sigungu, bjd_cd, area_m2)
    except Exception:
        conn.rollback()
        return None


# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=FarmCreateResponse, status_code=201)
def create_farm(data: FarmCreate, conn=Depends(get_db)):
    """농가 등록 + 자동 가치평가.

    lon/lat 제공 시 fn_farm_card로 필지 매칭 → bjd_cd·area_m2 자동 취득.
    미제공 시 area_m2 필수 (주소만으로 등록, 신뢰도 D).
    """
    warning: Optional[str] = None

    # ── 1. 필지 공간조인 (선택) ───────────────────────────────────────
    parcel_id = bjd_cd = sigungu = None
    sido = _extract_sido(data.address)
    area_m2 = data.area_m2

    if data.lon is not None and data.lat is not None:
        card = _call_farm_card(data.lon, data.lat, data.crop_code, sido, conn)
        if card:
            parcel_id, sido, sigungu, bjd_cd, area_m2 = card
            area_m2 = float(area_m2)
        else:
            warning = "좌표로 일치하는 과수원 필지를 찾지 못했습니다. 입력 면적으로 등록합니다."

    if area_m2 is None:
        raise HTTPException(
            status_code=422,
            detail="lon/lat 미입력 시 area_m2가 필요합니다.",
        )

    # ── 2. farm 행 삽입 ──────────────────────────────────────────────
    farm_id = _insert_farm(data, parcel_id, bjd_cd, area_m2, sido, sigungu, conn)
    _insert_assets(farm_id, data.assets, conn)
    conn.commit()

    # ── 3. 가치평가 (best-effort: 실패해도 farm은 저장됨) ────────────
    valuation: Optional[ValuationResponse] = None
    try:
        farm_input = load_farm_input(farm_id, conn)
        result = calc_total_value(farm_input, CURRENT_YEAR)
        _cache_valuation(farm_id, result, conn)
        valuation = _build_valuation_response(farm_id, result)
    except Exception as exc:
        warning = (warning or "") + f" 가치평가 산출 실패: {exc}"

    return FarmCreateResponse(farm_id=farm_id, valuation=valuation, warning=warning)


@router.get("/{farm_id}", response_model=FarmDetail)
def get_farm(farm_id: int, conn=Depends(get_db)):
    """농장 상세 조회."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, address, sido, crop_code::TEXT, tree_age, area_m2,
                   succession_type::TEXT, est_value_min, est_value_max,
                   confidence_grade::TEXT, status::TEXT, is_demo
            FROM farm WHERE id = %s
        """, (farm_id,))
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="farm not found")

    (id_, address, sido, crop_code, tree_age, area_m2,
     succession_type, val_min, val_max, grade, status, is_demo) = row

    with conn.cursor() as cur:
        cur.execute("""
            SELECT facility_code, area_m2, installed_year, condition_grade
            FROM farm_asset WHERE farm_id = %s ORDER BY id
        """, (farm_id,))
        asset_rows = cur.fetchall()

    return FarmDetail(
        id=id_,
        address=address,
        sido=sido,
        crop_code=crop_code,
        tree_age=tree_age,
        area_m2=float(area_m2),
        succession_type=succession_type,
        est_value_min=_to_만원(float(val_min)) if val_min else None,
        est_value_max=_to_만원(float(val_max)) if val_max else None,
        confidence_grade=grade,
        status=status,
        is_demo=is_demo,
        assets=[
            AssetSummary(
                facility_code=fc, area_m2=float(a_m2),
                installed_year=iy, condition_grade=cg,
            )
            for fc, a_m2, iy, cg in asset_rows
        ],
    )


@router.post("/{farm_id}/consult-requests", response_model=ConsultRequestResponse, status_code=201)
def create_consult_request(farm_id: int, data: ConsultRequestCreate, conn=Depends(get_db)):
    """청년농 → 농장 상담 신청."""
    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM farm WHERE id = %s", (farm_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="farm not found")

        cur.execute("SELECT 1 FROM young_farmer_profile WHERE id = %s", (data.young_farmer_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail="young_farmer not found")

        cur.execute("""
            INSERT INTO consult_request (farm_id, young_farmer_id, message)
            VALUES (%s, %s, %s)
            RETURNING id, status
        """, (farm_id, data.young_farmer_id, data.message))
        req_id, status = cur.fetchone()
    conn.commit()

    return ConsultRequestResponse(id=req_id, status=status)


@router.get("/{farm_id}/valuation", response_model=ValuationResponse)
def get_valuation(farm_id: int, conn=Depends(get_db)):
    """가치평가 결과 반환 (캐시 재사용 + 필요 시 재산출).

    farm 테이블에 캐시가 없으면 fresh 계산 후 저장.
    """
    # 캐시 확인
    with conn.cursor() as cur:
        cur.execute("""
            SELECT est_value_min, est_value_max, est_income_min,
                   est_income_max, confidence_grade::TEXT
            FROM farm WHERE id = %s
        """, (farm_id,))
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="farm not found")

    # 캐시 미존재 → fresh 산출
    if row[0] is None:
        try:
            farm_input = load_farm_input(farm_id, conn)
        except ValueError:
            raise HTTPException(status_code=404, detail="farm not found")

        result = calc_total_value(farm_input, CURRENT_YEAR)
        _cache_valuation(farm_id, result, conn)
        return _build_valuation_response(farm_id, result)

    # 캐시 존재 → 간이 응답 (full detail은 재산출)
    farm_input = load_farm_input(farm_id, conn)
    result = calc_total_value(farm_input, CURRENT_YEAR)
    return _build_valuation_response(farm_id, result)


@router.get("/{farm_id}/report.pdf")
def get_report_pdf(farm_id: int, conn=Depends(get_db)):
    """인수 검토 리포트 PDF (AI 요약/리스크 설명문 + 결정론적 가치평가 breakdown).

    ai_summary가 캐시돼 있으면 재사용(LLM 재호출 없음), 없으면 1회 생성 후 캐시.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT address, sido, succession_type::TEXT, ai_summary, ai_risk_notes
            FROM farm WHERE id = %s
        """, (farm_id,))
        row = cur.fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="farm not found")
    address, sido, succession_type, cached_summary, cached_risk_notes = row

    try:
        farm_input = load_farm_input(farm_id, conn)
    except ValueError:
        raise HTTPException(status_code=404, detail="farm not found")

    result = calc_total_value(farm_input, CURRENT_YEAR)
    risk_flags = derive_risk_flags(farm_input)

    if cached_summary is None:
        narrative = generate_narrative(ReportContext(
            crop_code=farm_input.crop_code,
            tree_age=farm_input.tree_age,
            area_m2=farm_input.area_m2,
            sido=sido or "",
            confidence_grade=result.confidence_grade,
            est_income_min=_to_만원(result.est_income_min),
            est_income_max=_to_만원(result.est_income_max),
            est_value_min=_to_만원(result.est_value_min),
            est_value_max=_to_만원(result.est_value_max),
            land_value_point=_to_만원(result.land_value_point),
            facility_value=_to_만원(result.facility_value),
            goodwill_min=_to_만원(result.goodwill_min),
            goodwill_max=_to_만원(result.goodwill_max),
            risk_flags=risk_flags,
        ))
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE farm SET ai_summary = %s, ai_risk_notes = %s, ai_generated_at = now()
                WHERE id = %s
            """, (narrative.summary, narrative.risk_notes, farm_id))
        conn.commit()
        ai_summary, ai_risk_notes = narrative.summary, narrative.risk_notes
    else:
        ai_summary, ai_risk_notes = cached_summary, cached_risk_notes

    goodwill_min_w = _to_만원(result.goodwill_min)
    goodwill_max_w = _to_만원(result.goodwill_max)
    goodwill_text = (
        "해당 없음" if goodwill_min_w == 0
        else f"{goodwill_min_w:,} ~ {goodwill_max_w:,}만원"
    )

    pdf_bytes = render_report_pdf({
        "sido": sido or "",
        "crop_name": CROP_NAMES.get(farm_input.crop_code, farm_input.crop_code),
        "tree_age": farm_input.tree_age,
        "generated_date": datetime.date.today().isoformat(),
        "confidence_grade": result.confidence_grade,
        "grade_desc": GRADE_DESC.get(result.confidence_grade, ""),
        "ai_summary": ai_summary,
        "ai_risk_notes": ai_risk_notes,
        "est_value_min": f"{_to_만원(result.est_value_min):,}",
        "est_value_max": f"{_to_만원(result.est_value_max):,}",
        "est_income_min": f"{_to_만원(result.est_income_min):,}",
        "est_income_max": f"{_to_만원(result.est_income_max):,}",
        "land_value_point": f"{_to_만원(result.land_value_point):,}",
        "facility_value": f"{_to_만원(result.facility_value):,}",
        "goodwill_text": goodwill_text,
        "risk_flags": risk_flags,
        "address": address,
        "area_m2": f"{farm_input.area_m2:,.0f}",
        "succession_name": SUCC_NAMES.get(succession_type, succession_type or "-"),
        "disclaimer": DISCLAIMER,
    })

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="farmbaton_report_{farm_id}.pdf"'},
    )
