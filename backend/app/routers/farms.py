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
from backend.app.routers.auth import get_current_farmer
from backend.app.schemas import (
    DISCLAIMER,
    AssetCreate,
    AssetSummary,
    ConsultRequestCreate,
    ConsultRequestDetail,
    ConsultRequestResponse,
    ConsultRequestStatusUpdate,
    FarmCreate,
    FarmCreateResponse,
    FarmDetail,
    FarmMatchItem,
    FarmMatchListResponse,
    FarmStatusUpdate,
    FarmStatusUpdateResponse,
    FarmSummary,
    ValuationResponse,
)
from backend.app.services.db_loader import load_farm_input, load_normal_year_price
from backend.app.services.pdf_render import render_report_pdf
from backend.app.services.report_ai import (
    CROP_NAMES,
    GRADE_DESC,
    MatchContext,
    ReportContext,
    fallback_match_explanation,
    generate_narrative,
)
from backend.app.services.valuation import (
    HIGH_DIFFICULTY_CROPS,
    FarmProfileForMatch,
    YoungFarmerInput,
    calc_match_score,
    calc_total_value,
    derive_risk_flags,
)

FARM_MATCH_TOP_N = 10  # 농장주 화면에 보여줄 매칭 청년농 최대 수

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
                 sido: Optional[str], sigungu: Optional[str], owner_id: int, conn) -> int:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO farm (
                address, sido, sigungu, bjd_cd, area_m2, crop_code,
                tree_age, succession_type, timing, annual_revenue,
                sales_channel, parcel_id, owner_id, status, is_demo
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'DRAFT',%s)
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
            owner_id,
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
def create_farm(data: FarmCreate, conn=Depends(get_db), owner_id: int = Depends(get_current_farmer)):
    """농가 등록 + 자동 가치평가 (로그인 필요 — 상담 신청을 받으려면 소유 식별 필수).

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
            parcel_id, sido, sigungu, bjd_cd, card_area_m2 = card
            card_area_m2 = float(card_area_m2)
            if data.area_m2 is not None and data.area_m2 > card_area_m2:
                # 좌표가 속한 필지 하나보다 사용자가 입력한 면적이 더 크면
                # 여러 필지로 구성된 농장일 가능성이 높음 — 단일 필지 면적으로
                # 덮어써 면적을 과소산정(→ 가치평가 축소)하지 않도록 입력값 우선.
                area_m2 = data.area_m2
                warning = (
                    f"입력 면적({data.area_m2:,.0f}㎡)이 좌표가 속한 필지 면적"
                    f"({card_area_m2:,.0f}㎡)보다 큽니다. 여러 필지로 구성된 농장으로 "
                    f"보고 입력 면적을 그대로 적용합니다."
                )
            else:
                area_m2 = card_area_m2
        else:
            warning = "좌표로 일치하는 과수원 필지를 찾지 못했습니다. 입력 면적으로 등록합니다."

    if area_m2 is None:
        raise HTTPException(
            status_code=422,
            detail="lon/lat 미입력 시 area_m2가 필요합니다.",
        )

    # ── 2. farm 행 삽입 ──────────────────────────────────────────────
    farm_id = _insert_farm(data, parcel_id, bjd_cd, area_m2, sido, sigungu, owner_id, conn)
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


@router.get("/mine", response_model=list[FarmSummary])
def get_my_farms(conn=Depends(get_db), owner_id: int = Depends(get_current_farmer)):
    """로그인한 농가가 등록한 농장 목록."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, address, sido, crop_code::TEXT, area_m2,
                   status::TEXT, est_value_min, est_value_max
            FROM farm WHERE owner_id = %s ORDER BY created_at DESC
        """, (owner_id,))
        rows = cur.fetchall()

    return [
        FarmSummary(
            id=id_, address=address, sido=sido, crop_code=crop_code,
            area_m2=float(area_m2), status=status,
            est_value_min=_to_만원(float(val_min)) if val_min is not None else None,
            est_value_max=_to_만원(float(val_max)) if val_max is not None else None,
        )
        for id_, address, sido, crop_code, area_m2, status, val_min, val_max in rows
    ]


@router.patch("/{farm_id}/status", response_model=FarmStatusUpdateResponse)
def update_farm_status(
    farm_id: int, data: FarmStatusUpdate,
    conn=Depends(get_db), owner_id: int = Depends(get_current_farmer),
):
    """농장 매칭 풀 공개(ACTIVE)/비공개(DRAFT) 전환 — 본인 농장만 가능.

    농가 등록 직후엔 DRAFT 상태라 청년농 매칭에 노출되지 않는다. 리포트를
    확인한 농가가 명시적으로 "매칭 풀에 공개"해야 ACTIVE로 바뀌어 매칭
    대상이 된다.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT owner_id, est_value_min FROM farm WHERE id = %s", (farm_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="farm not found")
        if row[0] != owner_id:
            raise HTTPException(status_code=403, detail="본인 농장만 변경할 수 있습니다.")
        if data.status == "ACTIVE" and row[1] is None:
            raise HTTPException(status_code=422, detail="가치평가가 먼저 산출되어야 공개할 수 있습니다.")

        cur.execute(
            "UPDATE farm SET status = %s::listing_status_t, updated_at = now() WHERE id = %s RETURNING id, status",
            (data.status, farm_id),
        )
        updated_id, updated_status = cur.fetchone()
    conn.commit()

    return FarmStatusUpdateResponse(id=updated_id, status=updated_status)


@router.get("/{farm_id}/matches", response_model=FarmMatchListResponse)
def get_farm_matches(
    farm_id: int, conn=Depends(get_db), owner_id: int = Depends(get_current_farmer),
):
    """농장주 화면용 — 이 농장에 매칭되는 청년농 리스트 (점수 내림차순, 상위 10명).

    calc_match_score는 양방향 함수라 청년농 화면(young_farmers.get_matches)과
    동일한 점수가 나온다. 본인 농장만 조회 가능.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT owner_id, sido, crop_code::TEXT, succession_type::TEXT, est_value_min
            FROM farm WHERE id = %s
        """, (farm_id,))
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="farm not found")
    farm_owner_id, sido, crop_code, succession_type, val_min = row
    if farm_owner_id != owner_id:
        raise HTTPException(status_code=403, detail="본인 농장만 조회할 수 있습니다.")
    if val_min is None:
        return FarmMatchListResponse(farm_id=farm_id, matches=[])

    farm_profile = FarmProfileForMatch(
        sido=sido,
        crop_code=crop_code,
        succession_type=succession_type or "SALE",
        est_value_min=float(val_min),
        crop_difficulty_high=(crop_code in HIGH_DIFFICULTY_CROPS),
    )

    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, pref_sido, pref_crop::TEXT, available_capital,
                   experience_years, policy_fund, pref_succession::TEXT
            FROM young_farmer_profile
        """)
        young_rows = cur.fetchall()

    items: list[tuple[float, FarmMatchItem]] = []
    for yf_id, pref_sido, pref_crop, capital, exp_yrs, policy_fund, pref_succ in young_rows:
        young = YoungFarmerInput(
            pref_sido=pref_sido,
            pref_crop=pref_crop,
            available_capital=float(capital),
            experience_years=int(exp_yrs),
            policy_fund=bool(policy_fund),
            pref_succession=pref_succ,
        )
        result = calc_match_score(young, farm_profile)
        explanation = fallback_match_explanation(MatchContext(
            pref_sido=pref_sido,
            pref_crop=pref_crop,
            farm_sido=sido,
            farm_crop=crop_code,
            pref_succession=pref_succ,
            succession_type=succession_type or "SALE",
            total_score=result.total_score,
            region_score=result.region_score,
            crop_score=result.crop_score,
            capital_score=result.capital_score,
            experience_score=result.experience_score,
            succession_score=result.succession_score,
            policy_score=result.policy_score,
            risk_penalty=result.risk_penalty,
        ))
        item = FarmMatchItem(
            young_farmer_id=yf_id,
            pref_sido=pref_sido,
            pref_crop=pref_crop,
            available_capital=_to_만원(float(capital)),
            experience_years=int(exp_yrs),
            pref_succession=pref_succ,
            policy_fund=bool(policy_fund),
            total_score=result.total_score,
            region_score=result.region_score,
            crop_score=result.crop_score,
            capital_score=result.capital_score,
            experience_score=result.experience_score,
            succession_score=result.succession_score,
            policy_score=result.policy_score,
            risk_penalty=result.risk_penalty,
            explanation=explanation,
        )
        items.append((result.total_score, item))

    items.sort(key=lambda x: x[0], reverse=True)
    top_items = [item for _, item in items[:FARM_MATCH_TOP_N]]

    return FarmMatchListResponse(farm_id=farm_id, matches=top_items)


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
            SELECT a.facility_code, COALESCE(f.facility_name, a.facility_code),
                   a.area_m2, a.installed_year, a.condition_grade
            FROM farm_asset a
            LEFT JOIN facility_std f ON f.facility_code = a.facility_code
            WHERE a.farm_id = %s ORDER BY a.id
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
        est_value_min=_to_만원(float(val_min)) if val_min is not None else None,
        est_value_max=_to_만원(float(val_max)) if val_max is not None else None,
        confidence_grade=grade,
        status=status,
        is_demo=is_demo,
        assets=[
            AssetSummary(
                facility_code=fc, facility_name=fname, area_m2=float(a_m2),
                installed_year=iy, condition_grade=cg,
            )
            for fc, fname, a_m2, iy, cg in asset_rows
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
            INSERT INTO consult_request (farm_id, young_farmer_id, message, contact_name, contact_phone)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, status
        """, (farm_id, data.young_farmer_id, data.message, data.contact_name, data.contact_phone))
        req_id, status = cur.fetchone()
    conn.commit()

    return ConsultRequestResponse(id=req_id, status=status)


@router.get("/{farm_id}/consult-requests", response_model=list[ConsultRequestDetail])
def list_consult_requests(farm_id: int, conn=Depends(get_db), owner_id: int = Depends(get_current_farmer)):
    """농가 상담함 — 본인 농장으로 들어온 상담 신청 목록."""
    with conn.cursor() as cur:
        cur.execute("SELECT owner_id FROM farm WHERE id = %s", (farm_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="farm not found")
        if row[0] != owner_id:
            raise HTTPException(status_code=403, detail="본인 농장만 조회할 수 있습니다.")

        cur.execute("""
            SELECT id, farm_id, contact_name, contact_phone, message, status, created_at
            FROM consult_request WHERE farm_id = %s ORDER BY created_at DESC
        """, (farm_id,))
        rows = cur.fetchall()

    return [
        ConsultRequestDetail(
            id=r[0], farm_id=r[1], contact_name=r[2], contact_phone=r[3],
            message=r[4], status=r[5], created_at=r[6].isoformat(),
        )
        for r in rows
    ]


@router.patch("/{farm_id}/consult-requests/{req_id}", response_model=ConsultRequestResponse)
def update_consult_request_status(
    farm_id: int, req_id: int, data: ConsultRequestStatusUpdate,
    conn=Depends(get_db), owner_id: int = Depends(get_current_farmer),
):
    """상담 신청 수락/거절 — 본인 농장의 신청만 변경 가능.

    수락(ACCEPTED) 시 farm.status를 MATCHED로 전환한다 — "수락 다음 단계가
    없다"는 피드백에 따라, 최소한 농장 목록에서 진행 상황이 보이도록.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT owner_id, status::TEXT FROM farm WHERE id = %s", (farm_id,))
        row = cur.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="farm not found")
        if row[0] != owner_id:
            raise HTTPException(status_code=403, detail="본인 농장만 변경할 수 있습니다.")
        farm_status = row[1]

        cur.execute("""
            UPDATE consult_request SET status = %s
            WHERE id = %s AND farm_id = %s
            RETURNING id, status
        """, (data.status, req_id, farm_id))
        updated = cur.fetchone()
        if updated is None:
            raise HTTPException(status_code=404, detail="consult_request not found")

        if data.status == "ACCEPTED" and farm_status != "MATCHED":
            cur.execute(
                "UPDATE farm SET status = 'MATCHED' WHERE id = %s RETURNING status::TEXT",
                (farm_id,),
            )
            farm_status = cur.fetchone()[0]
    conn.commit()

    return ConsultRequestResponse(id=updated[0], status=updated[1], farm_status=farm_status)


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


def _build_normal_year_text(crop_code: str, conn) -> str:
    """결정론적 평년가 안내문 — LLM 미사용(rule 1), 값 없으면 사유를 명시."""
    price, unit, _source = load_normal_year_price(crop_code, conn)
    crop_name = CROP_NAMES.get(crop_code, crop_code)
    if price is None:
        return (
            f"{crop_name} 작목은 가격 변동성이 커서 KAMIS도 평년가(5개년 중 "
            f"최고·최저 제외 3개년 평균)를 산출하지 못했습니다."
        )
    return (
        f"{price:,.0f}원/{unit} — KAMIS 평년 소매가"
        f"(5개년 중 최고·최저 제외 3개년 평균, {crop_name} 기준). "
        f"위 예상 연소득과는 별도 참고 지표입니다."
    )


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
    normal_year_text = _build_normal_year_text(farm_input.crop_code, conn)

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
        "normal_year_text": normal_year_text,
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
