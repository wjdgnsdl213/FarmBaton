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
    MyConsultRequestItem,
    SupportProgramItem,
    SupportProgramListResponse,
    YoungFarmerCreate,
    YoungProfileData,
)
from backend.app.services.report_ai import (
    CROP_NAMES,
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
OTHER_CROP_TOP_N = 3  # 희망 작목 외 탐색용 추천 수


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


def _partition_matches(
    matches: list[MatchItem], pref_crop: Optional[str]
) -> tuple[list[MatchItem], list[MatchItem]]:
    """희망 작목 농장을 본 목록으로, 다른 작목은 별도 탐색 목록으로 분리.

    작목 상관없음(None)이면 기존처럼 전체 농장을 점수순으로 합쳐 반환한다.
    각 그룹 내부 정렬은 기존 결정론적 매칭 점수를 그대로 사용한다.
    """
    ranked = sorted(matches, key=lambda item: item.total_score, reverse=True)
    if pref_crop is None:
        return ranked[:TOP_N], []

    preferred = [item for item in ranked if item.crop_code == pref_crop]
    other = [item for item in ranked if item.crop_code != pref_crop]
    return preferred[:TOP_N], other[:OTHER_CROP_TOP_N]


# ─────────────────────────────────────────────────────────────────────────────
# 엔드포인트
# ─────────────────────────────────────────────────────────────────────────────

def _require_young(user):
    # ADMIN은 청년농 플로우도 이용할 수 있다(운영/시연용).
    if user is None or user[1] not in ("YOUNG", "ADMIN"):
        raise HTTPException(status_code=403, detail="청년농 계정으로 로그인 후 이용할 수 있습니다.")
    return user[0]


@router.get("/me/profile", response_model=YoungProfileData)
def get_my_profile(conn=Depends(get_db), user=Depends(get_current_user_optional)):
    """로그인 청년농의 실제 프로필(내 정보). 농장주에게 노출되는 정보."""
    user_id = _require_young(user)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, pref_sido, pref_crop::TEXT, available_capital,
                   experience_years, policy_fund, pref_succession::TEXT, intro
            FROM young_farmer_profile WHERE user_id = %s ORDER BY id LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
    if row is None:
        return YoungProfileData()  # 아직 프로필 없음 → 기본값
    return YoungProfileData(
        young_farmer_id=row[0], pref_sido=row[1], pref_crop=row[2],
        available_capital=float(row[3] or 0), experience_years=int(row[4] or 0),
        policy_fund=bool(row[5]), pref_succession=row[6] or "SALE", intro=row[7],
    )


@router.put("/me/profile", response_model=YoungProfileData)
def put_my_profile(
    data: YoungProfileData, conn=Depends(get_db), user=Depends(get_current_user_optional),
):
    """청년농 실제 프로필 등록/갱신 (내 정보·가입 시). 1인 1프로필 upsert."""
    user_id = _require_young(user)
    vals = (
        data.pref_sido, data.pref_crop, data.available_capital,
        data.experience_years, data.policy_fund, data.pref_succession, data.intro,
    )
    with conn.cursor() as cur:
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
                    policy_fund = %s, pref_succession = %s::succession_type_t, intro = %s
                WHERE id = %s
            """, (*vals, yf_id))
        else:
            cur.execute("""
                INSERT INTO young_farmer_profile (
                    user_id, pref_sido, pref_crop, available_capital,
                    experience_years, policy_fund, pref_succession, intro
                ) VALUES (%s, %s, %s::crop_code_t, %s, %s, %s, %s::succession_type_t, %s)
                RETURNING id
            """, (user_id, *vals))
            yf_id = cur.fetchone()[0]
    conn.commit()
    return YoungProfileData(
        young_farmer_id=yf_id, pref_sido=data.pref_sido, pref_crop=data.pref_crop,
        available_capital=data.available_capital, experience_years=data.experience_years,
        policy_fund=data.policy_fund, pref_succession=data.pref_succession, intro=data.intro,
    )


@router.get("/me/consult-requests", response_model=list[MyConsultRequestItem])
def my_consult_requests(conn=Depends(get_db), user=Depends(get_current_user_optional)):
    """로그인한 청년농이 본인이 보낸 상담 신청 목록(농장 정보·상태 포함).

    수락(ACCEPTED)된 건은 프론트에서 채팅으로 이어진다.
    """
    if user is None or user[1] not in ("YOUNG", "ADMIN"):
        raise HTTPException(status_code=403, detail="청년농 계정으로 로그인이 필요합니다.")
    user_id = user[0]

    with conn.cursor() as cur:
        cur.execute("""
            SELECT cr.id, f.id, f.sido, f.crop_code::TEXT, f.address,
                   f.est_value_min, f.est_value_max, cr.status, cr.created_at
            FROM consult_request cr
            JOIN farm f ON f.id = cr.farm_id
            JOIN young_farmer_profile yp ON yp.id = cr.young_farmer_id
            WHERE yp.user_id = %s
            ORDER BY cr.created_at DESC
        """, (user_id,))
        rows = cur.fetchall()

    out = []
    for (cid, fid, sido, crop, addr, vmin, vmax, status, created) in rows:
        out.append(MyConsultRequestItem(
            id=cid, farm_id=fid,
            farm_label=f"{sido or ''} {CROP_NAMES.get(crop, crop)} 농장".strip(),
            address=addr or "",
            est_value_min=round(vmin / 10000) if vmin is not None else None,
            est_value_max=round(vmax / 10000) if vmax is not None else None,
            status=status, created_at=created.isoformat(),
        ))
    return out


def _score_farms(young: YoungFarmerInput, conn) -> list[MatchItem]:
    """검색 조건(young)으로 ACTIVE 농장을 모두 점수화해 점수순 반환 (미저장)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, address, sido, crop_code::TEXT, tree_age,
                   area_m2, succession_type::TEXT, est_value_min, est_value_max
            FROM farm WHERE status = 'ACTIVE' AND est_value_min IS NOT NULL
        """)
        farms = cur.fetchall()

    items: list[tuple[float, MatchItem]] = []
    for (fid, address, sido, crop_code, tree_age,
         area_m2, succession_type, val_min, val_max) in farms:
        if val_min is None:
            continue
        farm_profile = FarmProfileForMatch(
            sido=sido, crop_code=crop_code, succession_type=succession_type or "SALE",
            est_value_min=float(val_min),
            crop_difficulty_high=(crop_code in HIGH_DIFFICULTY_CROPS),
        )
        result = calc_match_score(young, farm_profile)
        explanation = fallback_match_explanation(MatchContext(
            pref_sido=young.pref_sido, pref_crop=young.pref_crop,
            farm_sido=sido, farm_crop=crop_code,
            pref_succession=young.pref_succession, succession_type=succession_type or "SALE",
            total_score=result.total_score, region_score=result.region_score,
            crop_score=result.crop_score, capital_score=result.capital_score,
            experience_score=result.experience_score, succession_score=result.succession_score,
            policy_score=result.policy_score, risk_penalty=result.risk_penalty,
        ))
        items.append((result.total_score, MatchItem(
            farm_id=fid, address=address, sido=sido, crop_code=crop_code, tree_age=tree_age,
            area_m2=float(area_m2), succession_type=succession_type,
            est_value_min=_to_만원(float(val_min)),
            est_value_max=_to_만원(float(val_max)) if val_max else 0,
            total_score=result.total_score, region_score=result.region_score,
            crop_score=result.crop_score, capital_score=result.capital_score,
            experience_score=result.experience_score, succession_score=result.succession_score,
            policy_score=result.policy_score, risk_penalty=result.risk_penalty,
            explanation=explanation,
        )))
    items.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in items]


@router.post("/match-search", response_model=MatchListResponse)
def match_search(
    data: YoungFarmerCreate, conn=Depends(get_db), user=Depends(get_current_user_optional),
):
    """매칭 검색 (탐색용, **미저장**) — 입력 조건으로 농장을 점수화해 반환.

    검색값은 프로필에 저장하지 않는다(궁금해서 다른 조건으로 검색해도 내
    프로필은 안 바뀜). 응답의 young_farmer_id는 **본인 실제 프로필 id**라,
    상담 신청 시엔 검색값이 아니라 내 정보 프로필이 농장주에게 전달된다.
    프로필이 아직 없으면 0 — 프론트는 내 정보 작성을 안내.
    """
    user_id = _require_young(user)
    young = YoungFarmerInput(
        pref_sido=data.pref_sido, pref_crop=data.pref_crop,
        available_capital=float(data.available_capital),
        experience_years=int(data.experience_years),
        policy_fund=bool(data.policy_fund), pref_succession=data.pref_succession,
    )
    scored = _score_farms(young, conn)
    matches, other_crop_matches = _partition_matches(scored, data.pref_crop)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM young_farmer_profile WHERE user_id = %s ORDER BY id LIMIT 1",
            (user_id,),
        )
        row = cur.fetchone()
    return MatchListResponse(
        young_farmer_id=(row[0] if row else 0),
        matches=matches,
        other_crop_matches=other_crop_matches,
    )


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
