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

from fastapi import APIRouter, Depends, HTTPException

from backend.app.db import get_db
from backend.app.schemas import (
    DISCLAIMER,
    AssetCreate,
    FarmCreate,
    FarmCreateResponse,
    FarmDetail,
    ValuationResponse,
)
from backend.app.services.db_loader import load_farm_input
from backend.app.services.valuation import calc_total_value

router = APIRouter(prefix="/api/farms", tags=["farms"])

CURRENT_YEAR = datetime.date.today().year


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


def _call_farm_card(lon: float, lat: float, crop_code: str, conn):
    """필지 매칭: ST_Contains 우선, 없으면 KNN 폴백.

    Returns (parcel_id, sido, sigungu, bjd_cd, area_m2) or None.
    마을 중심좌표는 개별 필지 안에 들어오지 않는 경우가 많아 KNN 폴백 필수.
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

            # 2차: KNN — 가장 가까운 과수원 필지 (폴백)
            cur.execute("""
                SELECT p.id, p.sido, p.sigungu, p.bjd_cd, p.area_m2
                FROM parcel p
                ORDER BY p.geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
                LIMIT 1
            """, (lon, lat))
            return cur.fetchone()
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
        card = _call_farm_card(data.lon, data.lat, data.crop_code, conn)
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
    )


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
