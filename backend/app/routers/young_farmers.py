"""
청년농 등록 · 매칭 리스트 라우터.

POST /api/young-farmers              — 청년농 프로필 등록
GET  /api/young-farmers/{id}/matches — 매칭 농장 리스트 (점수 내림차순)

매칭·지원사업 설명문은 여기서는 항상 결정론적 폴백 문장만 사용한다 — 화면을
열 때마다 Claude API를 여러 번 호출하면 응답이 느려지고 비용도 누적되므로,
풍부한 AI 설명은 PDF 리포트를 요청하는 시점(report.pdf, 1회 호출+캐싱)에만
넣는다.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from backend.app.db import get_db
from backend.app.routers.auth import get_current_user_optional
from backend.app.schemas import (
    MatchItem,
    MatchListResponse,
    SupportProgramItem,
    SupportProgramListResponse,
    YoungFarmerCreate,
    YoungFarmerCreateResponse,
)
from backend.app.services.report_ai import (
    MatchContext,
    ProgramPitchContext,
    fallback_match_explanation,
    fallback_program_pitch,
)
from backend.app.services.valuation import (
    HIGH_DIFFICULTY_CROPS,
    FarmProfileForMatch,
    YoungFarmerInput,
    calc_match_score,
)

router = APIRouter(prefix="/api/young-farmers", tags=["young-farmers"])

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


# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=YoungFarmerCreateResponse, status_code=201)
def create_young_farmer(
    data: YoungFarmerCreate,
    conn=Depends(get_db),
    user=Depends(get_current_user_optional),
):
    """청년농 프로필 등록.

    - 로그인한 YOUNG 사용자: 본인 계정에 연결된 프로필을 1개 유지(upsert) —
      재제출 시 같은 프로필을 갱신해 상담 신청이 본인 계정으로 귀속되게 한다.
    - 익명(로그인 안 함): 기존대로 익명 app_user + 프로필 생성 (데모 플로우 보존).
    """
    profile_vals = (
        data.pref_sido, data.pref_crop,
        data.available_capital, data.experience_years,
        data.policy_fund, data.pref_succession,
    )

    with conn.cursor() as cur:
        if user is not None and user[1] == "YOUNG":
            user_id = user[0]
            cur.execute(
                "SELECT id FROM young_farmer_profile WHERE user_id = %s ORDER BY id LIMIT 1",
                (user_id,),
            )
            existing = cur.fetchone()
            if existing is not None:
                yf_id = existing[0]
                cur.execute("""
                    UPDATE young_farmer_profile SET
                        pref_sido = %s, pref_crop = %s::crop_code_t,
                        available_capital = %s, experience_years = %s,
                        policy_fund = %s, pref_succession = %s::succession_type_t
                    WHERE id = %s
                """, (*profile_vals, yf_id))
                conn.commit()
                return YoungFarmerCreateResponse(young_farmer_id=yf_id)
        else:
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
        """, (user_id, *profile_vals))
        yf_id = cur.fetchone()[0]

    conn.commit()
    return YoungFarmerCreateResponse(young_farmer_id=yf_id)


@router.get("/{yf_id}/matches", response_model=MatchListResponse)
def get_matches(yf_id: int, conn=Depends(get_db)):
    """청년농 프로필 기반 매칭 농장 리스트 (상위 10개, 점수 내림차순).

    가치평가 캐시가 있는 ACTIVE 농장 전체를 대상으로 calc_match_score 산출.
    결과는 match_score 테이블에 UPSERT 캐시. 설명문은 결정론적 폴백 — AI
    설명은 PDF 리포트에서만 생성한다.
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

    # ── 3. 매칭 점수 산출 + 설명문(결정론적 폴백) ────────────────────
    items: list[tuple[float, MatchItem]] = []
    results_by_farm = {}  # farm_id -> MatchScoreResult (UPSERT에서 재사용)

    for (fid, address, sido, crop_code, tree_age,
         area_m2, succession_type, val_min, val_max) in farms:

        if val_min is None:
            continue

        farm_profile = FarmProfileForMatch(
            sido=sido,
            crop_code=crop_code,
            succession_type=succession_type or "SALE",
            est_value_min=float(val_min),
            crop_difficulty_high=(crop_code in HIGH_DIFFICULTY_CROPS),
        )
        result = calc_match_score(young, farm_profile)
        results_by_farm[fid] = result

        explanation = fallback_match_explanation(MatchContext(
            pref_sido=young.pref_sido,
            pref_crop=young.pref_crop,
            farm_sido=sido,
            farm_crop=crop_code,
            pref_succession=young.pref_succession,
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
            explanation=explanation,
        )
        items.append((result.total_score, item))

    # ── 4. 점수 내림차순 정렬, 상위 TOP_N ────────────────────────────
    items.sort(key=lambda x: x[0], reverse=True)
    top_items = [item for _, item in items[:TOP_N]]

    # ── 5. match_score 테이블 UPSERT (3단계 계산 결과 재사용) ─────────
    for item in top_items:
        _upsert_match_score(item.farm_id, yf_id, results_by_farm[item.farm_id], item.explanation, conn)
    conn.commit()

    return MatchListResponse(young_farmer_id=yf_id, matches=top_items)


@router.get("/{yf_id}/support-programs", response_model=SupportProgramListResponse)
def get_support_programs(yf_id: int, farm_id: Optional[int] = None, conn=Depends(get_db)):
    """청년농 프로필(또는 특정 매칭 농장)에 맞는 지원사업 추천.

    farm_id가 주어지면 그 농장의 실제 sido·crop_code로 필터링·추천 사유를
    맞춤화한다 (매칭 리스트의 각 농장 카드에서 호출하는 용도). 없으면 청년농
    프로필의 희망 지역·작목으로 필터링(페이지 진입 시 기본 추천).

    자격·금액 등 사실 정보는 support_program 테이블 원문 그대로 반환(필터링만
    결정론적 SQL). pitch도 결정론적 폴백 문장 — AI 설명은 PDF 리포트에서만.
    """
    with conn.cursor() as cur:
        cur.execute("""
            SELECT pref_sido, pref_crop::TEXT, policy_fund
            FROM young_farmer_profile WHERE id = %s
        """, (yf_id,))
        row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="young_farmer not found")
    pref_sido, pref_crop, policy_fund = row

    # farm_id가 있으면 그 농장의 실제 지역·작목을 필터 기준으로 사용
    sido_filter, crop_filter = pref_sido, pref_crop
    if farm_id is not None:
        with conn.cursor() as cur:
            cur.execute("SELECT sido, crop_code::TEXT FROM farm WHERE id = %s", (farm_id,))
            farm_row = cur.fetchone()
        if farm_row is None:
            raise HTTPException(status_code=404, detail="farm not found")
        sido_filter, crop_filter = farm_row

    with conn.cursor() as cur:
        cur.execute("""
            SELECT program_code, name, description, amount_text, apply_url
            FROM support_program
            WHERE (target_sido IS NULL OR %s IS NULL OR target_sido = %s)
              AND (target_crop IS NULL OR %s IS NULL OR target_crop = %s)
              AND target_role IN ('YOUNG', 'ANY')
            ORDER BY program_code
        """, (sido_filter, sido_filter, crop_filter, crop_filter))
        rows = cur.fetchall()

    programs = []
    for program_code, name, description, amount_text, apply_url in rows:
        pitch = fallback_program_pitch(ProgramPitchContext(
            program_name=name,
            program_description=description,
            amount_text=amount_text,
            pref_sido=sido_filter,
            pref_crop=crop_filter,
            policy_fund=bool(policy_fund),
        ))
        programs.append(SupportProgramItem(
            program_code=program_code, name=name, description=description,
            amount_text=amount_text, apply_url=apply_url, pitch=pitch,
        ))

    return SupportProgramListResponse(young_farmer_id=yf_id, programs=programs)
