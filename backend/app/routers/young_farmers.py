"""
청년농 등록 · 매칭 리스트 라우터.

POST /api/young-farmers              — 청년농 프로필 등록
GET  /api/young-farmers/{id}/matches — 매칭 농장 리스트 (점수 내림차순)
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.db import get_db
from backend.app.schemas import (
    MatchItem,
    MatchListResponse,
    YoungFarmerCreate,
    YoungFarmerCreateResponse,
)
from backend.app.services.report_ai import MatchContext, generate_match_explanation
from backend.app.services.valuation import (
    FarmProfileForMatch,
    YoungFarmerInput,
    calc_match_score,
)

router = APIRouter(prefix="/api/young-farmers", tags=["young-farmers"])

# APPLE은 기술 난이도가 높은 작목 (밀식재배 관리 등)
_HIGH_DIFFICULTY_CROPS = {"APPLE"}

TOP_N = 10  # 매칭 리스트 최대 반환 수


# ─────────────────────────────────────────────────────────────────────────────
# 내부 헬퍼
# ─────────────────────────────────────────────────────────────────────────────

def _to_만원(value: float) -> int:
    return round(value / 10_000)


def _upsert_match_score(farm_id: int, yf_id: int, result, explanation: Optional[str], conn) -> None:
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO match_score (
                farm_id, young_farmer_id, total_score,
                region_score, crop_score, capital_score,
                experience_score, succession_score, policy_score, risk_penalty,
                explanation
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (farm_id, young_farmer_id) DO UPDATE SET
                total_score      = EXCLUDED.total_score,
                region_score     = EXCLUDED.region_score,
                crop_score       = EXCLUDED.crop_score,
                capital_score    = EXCLUDED.capital_score,
                experience_score = EXCLUDED.experience_score,
                succession_score = EXCLUDED.succession_score,
                policy_score     = EXCLUDED.policy_score,
                risk_penalty     = EXCLUDED.risk_penalty,
                explanation      = EXCLUDED.explanation,
                computed_at      = now()
        """, (
            farm_id, yf_id, result.total_score,
            result.region_score, result.crop_score, result.capital_score,
            result.experience_score, result.succession_score,
            result.policy_score, result.risk_penalty, explanation,
        ))


def _fetch_cached_explanations(farm_ids: list[int], yf_id: int, conn) -> dict[int, str]:
    """이미 생성된 매칭 설명문 캐시 조회 (LLM 재호출 방지)."""
    if not farm_ids:
        return {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT farm_id, explanation FROM match_score
            WHERE young_farmer_id = %s AND farm_id = ANY(%s) AND explanation IS NOT NULL
        """, (yf_id, farm_ids))
        return dict(cur.fetchall())


# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=YoungFarmerCreateResponse, status_code=201)
def create_young_farmer(data: YoungFarmerCreate, conn=Depends(get_db)):
    """청년농 프로필 등록."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO app_user (role, is_demo) VALUES ('YOUNG', FALSE) RETURNING id"
        )
        user_id = cur.fetchone()[0]

        cur.execute("""
            INSERT INTO young_farmer_profile (
                user_id, pref_sido, pref_crop,
                available_capital, experience_years,
                policy_fund, pref_succession
            ) VALUES (%s, %s, %s::crop_code_t, %s, %s, %s, %s::succession_type_t)
            RETURNING id
        """, (
            user_id, data.pref_sido, data.pref_crop,
            data.available_capital, data.experience_years,
            data.policy_fund, data.pref_succession,
        ))
        yf_id = cur.fetchone()[0]

    conn.commit()
    return YoungFarmerCreateResponse(young_farmer_id=yf_id)


@router.get("/{yf_id}/matches", response_model=MatchListResponse)
def get_matches(yf_id: int, conn=Depends(get_db)):
    """청년농 프로필 기반 매칭 농장 리스트 (상위 10개, 점수 내림차순).

    가치평가 캐시가 있는 ACTIVE 농장 전체를 대상으로 calc_match_score 산출.
    결과는 match_score 테이블에 UPSERT 캐시.
    """
    # ── 1. 청년농 프로필 로드 ─────────────────────────────────────────
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pref_sido, pref_crop::TEXT, available_capital,
                   experience_years, policy_fund, pref_succession::TEXT
            FROM young_farmer_profile
            WHERE id = %s
        """, (yf_id,))
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="young_farmer not found")

    pref_sido, pref_crop, capital, exp_yrs, policy_fund, pref_succ = row
    young = YoungFarmerInput(
        pref_sido=pref_sido,
        pref_crop=pref_crop,
        available_capital=float(capital),
        experience_years=int(exp_yrs),
        policy_fund=bool(policy_fund),
        pref_succession=pref_succ,
    )

    # ── 2. 매칭 대상 농장 목록 (가치평가 캐시 있는 ACTIVE) ───────────
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, address, sido, crop_code::TEXT, tree_age,
                   area_m2, succession_type::TEXT,
                   est_value_min, est_value_max
            FROM farm
            WHERE status = 'ACTIVE'
              AND est_value_min IS NOT NULL
        """)
        farms = cur.fetchall()

    if not farms:
        return MatchListResponse(young_farmer_id=yf_id, matches=[])

    # ── 3. 매칭 점수 산출 ────────────────────────────────────────────
    items: list[tuple[float, MatchItem]] = []

    for (fid, address, sido, crop_code, tree_age,
         area_m2, succession_type, val_min, val_max) in farms:

        if val_min is None:
            continue

        farm_profile = FarmProfileForMatch(
            sido=sido,
            crop_code=crop_code,
            succession_type=succession_type or "SALE",
            est_value_min=float(val_min),
            crop_difficulty_high=(crop_code in _HIGH_DIFFICULTY_CROPS),
        )
        result = calc_match_score(young, farm_profile)

        item = MatchItem(
            farm_id=fid,
            address=address,
            sido=sido,
            crop_code=crop_code,
            tree_age=tree_age,
            area_m2=float(area_m2),
            succession_type=succession_type,
            est_value_min=_to_만원(float(val_min)),
            est_value_max=_to_만원(float(val_max)) if val_max else 0,
            total_score=result.total_score,
            region_score=result.region_score,
            crop_score=result.crop_score,
            capital_score=result.capital_score,
            experience_score=result.experience_score,
            succession_score=result.succession_score,
            policy_score=result.policy_score,
            risk_penalty=result.risk_penalty,
        )
        items.append((result.total_score, item))

    # ── 4. 점수 내림차순 정렬, 상위 TOP_N ────────────────────────────
    items.sort(key=lambda x: x[0], reverse=True)
    top_items = [item for _, item in items[:TOP_N]]

    # ── 5. 매칭 설명문 (캐시 우선, 없으면 생성) — 실제 반환되는 TOP_N만 ──
    cached = _fetch_cached_explanations([item.farm_id for item in top_items], yf_id, conn)
    for item in top_items:
        if item.farm_id in cached:
            item.explanation = cached[item.farm_id]
        else:
            item.explanation = generate_match_explanation(MatchContext(
                pref_sido=young.pref_sido,
                pref_crop=young.pref_crop,
                farm_sido=item.sido,
                farm_crop=item.crop_code,
                pref_succession=young.pref_succession,
                succession_type=item.succession_type or "SALE",
                total_score=item.total_score,
                region_score=item.region_score,
                crop_score=item.crop_score,
                capital_score=item.capital_score,
                experience_score=item.experience_score,
                succession_score=item.succession_score,
                policy_score=item.policy_score,
                risk_penalty=item.risk_penalty,
            ))

    # ── 6. match_score 테이블 UPSERT ────────────────────────────────
    with conn.cursor() as cur:
        for score, item in items[:TOP_N]:
            farm_profile = FarmProfileForMatch(
                sido=item.sido,
                crop_code=item.crop_code,
                succession_type=item.succession_type or "SALE",
                est_value_min=float(item.est_value_min) * 10_000,
                crop_difficulty_high=(item.crop_code in _HIGH_DIFFICULTY_CROPS),
            )
            result = calc_match_score(young, farm_profile)
            _upsert_match_score(item.farm_id, yf_id, result, item.explanation, conn)
    conn.commit()

    return MatchListResponse(young_farmer_id=yf_id, matches=top_items)
